"""Upsert de imóveis vindos do eGO Real Estate para a tabela `imoveis`
(projecto secundário Supabase). Full-sync paginado sempre (ver nota em
`egorealestate.py` sobre o endpoint /Latest estar avariado do lado do eGO).
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import egorealestate, egorealestate_crm

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
_INT_SENTINEL = -2147483648  # eGO usa INT32_MIN para "sem valor" em campos int (Rooms, Floor, ...)
_BUSINESS_VENDA = {"For sale", "Venda"}
_BUSINESS_ARRENDAMENTO = {"To rent", "Arrendamento", "Aluguer"}


def _int_or_none(v):
    return None if v is None or v == _INT_SENTINEL else v


def _utc_iso(value: str | None) -> str | None:
    """eGO devolve timestamps sem offset (mas são UTC, per doc oficial)."""
    if not value:
        return None
    return value if value.endswith("Z") or "+" in value[10:] else f"{value}+00:00"


def _map_property(p: dict) -> dict:
    venda_preco = None
    arrendamento_preco = None
    for biz in p.get("PropertyBusiness") or []:
        prices = biz.get("Prices") or []
        valor = prices[0].get("PriceValue") if prices else None
        nome = biz.get("BusinessName")
        if nome in _BUSINESS_VENDA:
            venda_preco = valor
        elif nome in _BUSINESS_ARRENDAMENTO:
            arrendamento_preco = valor

    return {
        "ego_id": p.get("ID"),
        "imovel_ref": p.get("Reference"),
        "natureza": p.get("Type"),
        "estado": p.get("Condition"),
        "disponibilidade": p.get("Availability"),
        "quartos": _int_or_none(p.get("Rooms")),
        "casas_banho": _int_or_none(p.get("Bathrooms")),
        "piso": str(p["Floor"]) if _int_or_none(p.get("Floor")) is not None else None,
        "num_pisos": _int_or_none(p.get("Floors")),
        "fracao": p.get("Fraction") or None,
        "area_util": p.get("NetArea"),
        "area_bruta": p.get("GrossArea"),
        "area_terreno": p.get("LandArea"),
        "concelho": p.get("Municipality"),
        "freguesia": p.get("Parish"),
        "zona": p.get("Zone"),
        "morada": p.get("Address"),
        "codigo_postal": p.get("ZipCode"),
        "titulo": p.get("Title"),
        "descricao": p.get("Description"),
        "venda_preco": venda_preco,
        "arrendamento_preco": arrendamento_preco,
        "foto_principal": p.get("Thumbnail"),
        "fotos": [img["Thumbnail"] for img in (p.get("Images") or []) if img.get("Thumbnail")],
        "ego_atualizado_em": _utc_iso(p.get("LastModified")),
        "fonte": "egorealestate",
    }


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


async def _existing_refs(refs: list[str]) -> set[str]:
    def _fetch():
        return get_supabase().table("imoveis").select("imovel_ref").in_("imovel_ref", refs).execute()

    resp = await _run(_fetch)
    return {r["imovel_ref"] for r in resp.data}


async def _existing_ego_ids(disponibilidades: set[str]) -> set[int]:
    """ego_ids que já achávamos publicados (fonte='egorealestate' com
    disponibilidade num dos valores que a API pública realmente devolve —
    hoje só Disponível/Vendido, mas evita hardcode). Filtra por
    disponibilidade porque `validar_disponibilidade_crm` também marca
    fonte='egorealestate' em imóveis Por validar/Reservado/Arrendado que a
    API pública nunca devolve por definição — sem este filtro seriam todos
    sinalizados como "deixaram de estar publicados" indevidamente."""
    if not disponibilidades:
        return set()

    def _fetch():
        return (
            get_supabase()
            .table("imoveis")
            .select("ego_id")
            .eq("fonte", "egorealestate")
            .in_("disponibilidade", list(disponibilidades))
            .not_.is_("ego_id", "null")
            .execute()
        )

    resp = await _run(_fetch)
    return {r["ego_id"] for r in resp.data}


_TAREFA_TITULO_PREFIX = "eGO deixou de publicar"


async def _flag_unpublished(missing_ego_ids: set[int]) -> tuple[int, list[dict]]:
    """`/v1/Properties/Latest` reporta o ID como alterado, mas `/v1/Properties`
    já não o devolve — a API só devolve imóveis publicados. Não sabemos qual o
    estado real (Por validar / Retirado / Em Prospecção), por isso não
    adivinhamos `disponibilidade`: criamos uma tarefa para o corretor confirmar
    no CRM, uma vez por imóvel."""
    if not missing_ego_ids:
        return 0, []

    def _fetch_rows():
        return (
            get_supabase()
            .table("imoveis")
            .select("imovel_ref")
            .in_("ego_id", list(missing_ego_ids))
            .execute()
        )

    resp = await _run(_fetch_rows)
    refs = [r["imovel_ref"] for r in resp.data if r["imovel_ref"]]
    if not refs:
        return 0, []

    def _fetch_tarefas_abertas():
        return (
            get_supabase()
            .table("agente_tarefas")
            .select("imovel_ref")
            .eq("estado", "pendente")
            .like("titulo", f"{_TAREFA_TITULO_PREFIX}%")
            .in_("imovel_ref", refs)
            .execute()
        )

    resp2 = await _run(_fetch_tarefas_abertas)
    ja_sinalizados = {r["imovel_ref"] for r in resp2.data}
    novos = [ref for ref in refs if ref not in ja_sinalizados]
    if not novos:
        return 0, []

    tarefas = [
        {
            "titulo": f"{_TAREFA_TITULO_PREFIX} — {ref}",
            "descricao": "eGO reportou alteração neste imóvel mas já não o devolve na listagem pública. Confirmar o estado real no CRM (Por validar / Retirado / Em Prospecção) e actualizar manualmente.",
            "imovel_ref": ref,
        }
        for ref in novos
    ]

    def _insert():
        return get_supabase().table("agente_tarefas").insert(tarefas).execute()

    await _run(_insert)
    detalhes = [{"imovel_ref": ref, "tipo": "nao_publicado", "descricao": "deixou de estar publicado no eGO, tarefa criada"} for ref in novos]
    return len(novos), detalhes


_TAREFA_DIVERGENCIA_PREFIX = "eGO disponibilidade divergente"


async def _flag_divergencia(refs: list[str], motivo: str, tipo: str) -> list[dict]:
    """Linha marcada 'Disponível' que não aparece na lista CRM-Disponível e
    que não conseguimos reler automaticamente (sem `ego_id` conhecido, ou sem
    permissão de acesso à ficha no CRM) — sinalizar em vez de adivinhar."""
    if not refs:
        return []

    def _fetch_tarefas_abertas():
        return (
            get_supabase()
            .table("agente_tarefas")
            .select("imovel_ref")
            .eq("estado", "pendente")
            .like("titulo", f"{_TAREFA_DIVERGENCIA_PREFIX}%")
            .in_("imovel_ref", refs)
            .execute()
        )

    resp = await _run(_fetch_tarefas_abertas)
    ja_sinalizados = {r["imovel_ref"] for r in resp.data}
    novos = [ref for ref in refs if ref not in ja_sinalizados]
    if not novos:
        return []

    tarefas = [
        {
            "titulo": f"{_TAREFA_DIVERGENCIA_PREFIX} — {ref}",
            "descricao": f"Marcado 'Disponível' no Supabase mas não aparece na lista de Disponíveis do CRM. {motivo} Confirmar manualmente no CRM.",
            "imovel_ref": ref,
        }
        for ref in novos
    ]

    def _insert():
        return get_supabase().table("agente_tarefas").insert(tarefas).execute()

    await _run(_insert)
    return [{"imovel_ref": ref, "tipo": tipo, "descricao": "tarefa criada"} for ref in novos]


async def validar_disponibilidade_crm() -> tuple[int, list[dict]]:
    """Cruza o backoffice autenticado do eGO (visibilidade total, incl.
    imóveis nunca publicados) com a tabela `imoveis`. Ao contrário da Web API
    pública, aqui o valor de `disponibilidade` é conhecido com certeza, por
    isso corrige-se directamente em vez de só sinalizar. Três sub-casos:
    1) CRM diz Disponível, sem linha local → cria linha nova (fetch_detail).
    2) CRM diz X, linha local diz outra coisa → corrige directamente.
    3) Linha local diz Disponível, CRM não a lista como Disponível → relê o
       estado real via fetch_detail (se soubermos o ego_id) e corrige."""
    if not settings.egorealestate_crm_username or not settings.egorealestate_crm_password:
        return 0, []

    detalhes: list[dict] = []

    async with egorealestate_crm.authenticated_client() as client:
        await egorealestate_crm._login(client)
        crm_items = await egorealestate_crm.fetch_all(client)
        if not crm_items:
            return 0, []

        # Calculado ANTES do dedup abaixo: se uma referência duplicada tem uma
        # cópia Disponível e outra copia noutro estado, ainda conta como
        # Disponível para os Casos 1/3 — só a Caso 2 (update de 1 linha) é
        # que só pode aplicar um dos dois, daí o dedup ser só para essa parte.
        crm_disponiveis_refs = {i["imovel_ref"] for i in crm_items if i["imovel_ref"] and i["crm_disponibilidade"] == "Disponível"}

        # O eGO por vezes devolve a mesma Reference em 2 propriedades distintas
        # (mesmo problema já conhecido do upsert da Web API, ver sync_egorealestate_api)
        # — a nossa tabela só tem uma linha por imovel_ref, por isso mantemos só a
        # última ocorrência em vez de aplicar as duas (evitaria oscilar a cada run).
        by_ref: dict[str, dict] = {}
        for i in crm_items:
            if not i["imovel_ref"]:
                continue
            if i["imovel_ref"] in by_ref and by_ref[i["imovel_ref"]] != i:
                logger.warning("imovel_ref duplicado no CRM eGO: %s (ego_id %s ignorado)", i["imovel_ref"], by_ref[i["imovel_ref"]]["ego_id"])
            by_ref[i["imovel_ref"]] = i
        crm_items = list(by_ref.values())
        refs = list(by_ref)

        def _fetch_existentes():
            return (
                get_supabase()
                .table("imoveis")
                .select("imovel_ref,disponibilidade,ego_id,fonte")
                .in_("imovel_ref", refs)
                .execute()
            )

        resp = await _run(_fetch_existentes)
        existentes = {r["imovel_ref"]: r for r in resp.data}

        # Caso 2: linha já existe, corrigir directamente se divergir.
        updates = []
        for item in crm_items:
            atual = existentes.get(item["imovel_ref"])
            if not atual:
                continue
            muda_disponibilidade = atual["disponibilidade"] != item["crm_disponibilidade"]
            muda_ego_id = atual["ego_id"] is None and item["ego_id"] is not None
            muda_fonte = atual["fonte"] in ("manual", "csv") and item["ego_id"] is not None
            if not (muda_disponibilidade or muda_ego_id or muda_fonte):
                continue
            update = {"imovel_ref": item["imovel_ref"], "disponibilidade": item["crm_disponibilidade"]}
            alteracoes = {}
            if muda_disponibilidade:
                alteracoes["disponibilidade"] = {"de": atual["disponibilidade"], "para": item["crm_disponibilidade"]}
            if muda_ego_id:
                update["ego_id"] = item["ego_id"]
                alteracoes["ego_id"] = {"de": atual["ego_id"], "para": item["ego_id"]}
            if muda_fonte:
                update["fonte"] = "egorealestate"
                alteracoes["fonte"] = {"de": atual["fonte"], "para": "egorealestate"}
            updates.append(update)
            detalhes.append({"imovel_ref": item["imovel_ref"], "tipo": "corrigido_crm", "alteracoes": alteracoes})

        if updates:
            def _apply_updates():
                for u in updates:
                    get_supabase().table("imoveis").update(u).eq("imovel_ref", u["imovel_ref"]).execute()

            await _run(_apply_updates)

        # Caso 1: CRM diz Disponível, sem linha local — criar.
        criados = []
        for item in crm_items:
            if item["imovel_ref"] not in crm_disponiveis_refs or existentes.get(item["imovel_ref"]) or not item["ego_id"]:
                continue
            detail = await egorealestate_crm.fetch_detail(client, item["ego_id"])
            if not detail or not detail["imovel_ref"]:
                continue
            criados.append(detail)
            detalhes.append({"imovel_ref": detail["imovel_ref"], "tipo": "criado_crm"})

        if criados:
            def _insert_criados():
                return get_supabase().table("imoveis").insert(criados).execute()

            await _run(_insert_criados)

        # Caso 3: linha local diz Disponível mas não está na lista CRM-Disponível.
        def _fetch_disponiveis_locais():
            return (
                get_supabase()
                .table("imoveis")
                .select("imovel_ref,ego_id")
                .eq("disponibilidade", "Disponível")
                .execute()
            )

        resp_disp = await _run(_fetch_disponiveis_locais)
        stale = [r for r in resp_disp.data if r["imovel_ref"] not in crm_disponiveis_refs]

        sem_ego_id = [r["imovel_ref"] for r in stale if not r["ego_id"]]
        detalhes.extend(await _flag_divergencia(
            sem_ego_id, "Nunca foi ligado a um ego_id para reler o estado real automaticamente.", "divergencia_sem_ego_id",
        ))

        sem_acesso: list[str] = []
        corrigidos_stale = 0
        for row in stale:
            if not row["ego_id"]:
                continue
            detail = await egorealestate_crm.fetch_detail(client, row["ego_id"])
            if not detail or not detail.get("disponibilidade"):
                # ego_id conhecido mas devolve "Você não pode consultar este
                # imóvel..." — confirmado ao vivo (caso FH2491F, e depois
                # reconfirmado em massa 2026-07-23 nas 6 refs Panoramic
                # Pool/FH2479C) que a causa mais comum é o ego_id estar
                # desactualizado (imóvel recriado no eGO com novo ID), não
                # permissão real. `find_by_ref` (endpoint de pesquisa livre,
                # campo `FreeText`, sem filtro de status) reencontra o ego_id
                # novo pela referência — se devolver correspondência exacta,
                # o valor é tão certo como o resto desta função (Casos 1/2),
                # por isso corrige-se directamente em vez de só sinalizar.
                encontrado = await egorealestate_crm.find_by_ref(client, row["imovel_ref"])
                if not encontrado:
                    sem_acesso.append(row["imovel_ref"])
                    continue
                novo_valor = encontrado["crm_disponibilidade"]

                def _apply_reencontrado(ref=row["imovel_ref"], valor=novo_valor, ego_id=encontrado["ego_id"]):
                    get_supabase().table("imoveis").update({"disponibilidade": valor, "ego_id": ego_id}).eq("imovel_ref", ref).execute()

                await _run(_apply_reencontrado)
                corrigidos_stale += 1
                detalhes.append({
                    "imovel_ref": row["imovel_ref"], "tipo": "corrigido_crm",
                    "alteracoes": {
                        "disponibilidade": {"de": "Disponível", "para": novo_valor},
                        "ego_id": {"de": row["ego_id"], "para": encontrado["ego_id"]},
                    },
                })
                continue
            if detail["disponibilidade"] == "Disponível":
                continue
            novo_valor = detail["disponibilidade"]

            def _apply_stale(ref=row["imovel_ref"], valor=novo_valor):
                get_supabase().table("imoveis").update({"disponibilidade": valor}).eq("imovel_ref", ref).execute()

            await _run(_apply_stale)
            corrigidos_stale += 1
            detalhes.append({
                "imovel_ref": row["imovel_ref"], "tipo": "corrigido_crm",
                "alteracoes": {"disponibilidade": {"de": "Disponível", "para": novo_valor}},
            })

        detalhes.extend(await _flag_divergencia(
            sem_acesso,
            "O ego_id guardado já não dá acesso à ficha no CRM — provavelmente desactualizado (imóvel recriado com novo ID no eGO), possivelmente também permissão restrita a outro agente. Confirmar a referência real no CRM e actualizar o ego_id manualmente se necessário.",
            "divergencia_sem_acesso",
        ))

    total = len(updates) + len(criados) + corrigidos_stale
    return total, detalhes


async def _log_execucao(tipo: str, resumo: dict, detalhes: list[dict]) -> None:
    def _insert():
        return get_supabase().table("agente_sync_log").insert({
            "tipo": tipo, "resumo": resumo, "detalhes": detalhes,
        }).execute()

    await _run(_insert)


async def sync_egorealestate_crm() -> dict:
    """Só a validação via CRM backoffice (`validar_disponibilidade_crm`) —
    fonte de verdade da `disponibilidade`, incl. imóveis nunca publicados.
    Acção separada da pull da Web API (ver `sync_egorealestate_api`) porque
    são scrapers/fontes distintas, disparados independentemente no painel."""
    if not settings.egorealestate_crm_username or not settings.egorealestate_crm_password:
        raise RuntimeError("EGOREALESTATE_CRM_USERNAME/PASSWORD não configuradas.")

    corrigidos, detalhes = await validar_disponibilidade_crm()
    resumo = {"criados": 0, "atualizados": 0, "erros": 0, "nao_publicados": 0, "corrigidos": corrigidos}
    await _log_execucao("egorealestate_crm", resumo, detalhes)
    return resumo


async def sync_egorealestate_api() -> dict:
    """`/v1/Properties/Latest` (sync incremental) está avariado do lado do
    eGO — testado ao vivo, ignora `Since` sempre. Por isso corre-se sempre
    full-sync paginado (portefólio publicado é pequeno, ~55 imóveis).
    Só a Web API pública (imóveis publicados) — a validação via CRM
    backoffice é uma acção separada, ver `sync_egorealestate_crm`."""
    if not settings.egorealestate_api_key:
        raise RuntimeError("EGOREALESTATE_API_KEY não configurada.")

    detalhes: list[dict] = []

    properties: list[dict] = []
    page = 1
    while True:
        batch, total = await egorealestate.get_properties_page(page, PAGE_SIZE)
        properties.extend(batch)
        if not batch or len(properties) >= total:
            break
        page += 1

    # Um ego_id que já conhecíamos (fonte='egorealestate') mas que não veio
    # nesta pull completa foi despublicado — a API só devolve publicados, e
    # sem full-sync não saberíamos se foi porque mudou de página ou porque
    # deixou mesmo de estar publicado. Sinalizar em vez de deixar o registo
    # antigo por actualizar.
    seen_ids = {p.get("ID") for p in properties if p.get("ID")}
    seen_disponibilidades = {p.get("Availability") for p in properties if p.get("Availability")}
    existing_ego_ids = await _existing_ego_ids(seen_disponibilidades)
    missing = existing_ego_ids - seen_ids
    nao_publicados, det_nao_publicados = await _flag_unpublished(missing)
    detalhes.extend(det_nao_publicados)

    if not properties:
        resumo = {"criados": 0, "atualizados": 0, "erros": 0, "nao_publicados": nao_publicados, "corrigidos": 0}
        await _log_execucao("egorealestate_api", resumo, detalhes)
        return resumo

    now_iso = datetime.now(timezone.utc).isoformat()
    records = []
    erros = 0
    for p in properties:
        try:
            record = _map_property(p)
            if not record["imovel_ref"]:
                raise ValueError("propriedade eGO sem Reference")
            record["ego_atualizado_em"] = record["ego_atualizado_em"] or now_iso
            records.append(record)
        except Exception:
            logger.exception("Falha a mapear propriedade eGO %s", p.get("ID"))
            erros += 1

    # imovel_ref é a PK real da tabela (chave partilhada com o resto do
    # sistema); upsert por ego_id colidiria com linhas já existentes por
    # referência (ex: entradas manuais que o eGO agora também reporta).
    # O eGO ocasionalmente devolve o mesmo Reference em 2 propriedades
    # (dado sujo do lado deles) — Postgres não aceita ON CONFLICT duplicado
    # no mesmo batch, por isso mantemos só a última ocorrência.
    by_ref: dict[str, dict] = {}
    for r in records:
        if r["imovel_ref"] in by_ref:
            logger.warning("imovel_ref duplicado no batch eGO: %s (ego_id %s ignorado)", r["imovel_ref"], by_ref[r["imovel_ref"]]["ego_id"])
        by_ref[r["imovel_ref"]] = r
    records = list(by_ref.values())

    refs = list(by_ref)
    existentes = await _existing_refs(refs)

    def _upsert():
        return get_supabase().table("imoveis").upsert(records, on_conflict="imovel_ref").execute()

    await _run(_upsert)

    criados = sum(1 for r in records if r["imovel_ref"] not in existentes)
    atualizados = len(records) - criados
    detalhes.extend(
        {"imovel_ref": r["imovel_ref"], "tipo": "criado" if r["imovel_ref"] not in existentes else "atualizado"}
        for r in records
    )
    resumo = {"criados": criados, "atualizados": atualizados, "erros": erros, "nao_publicados": nao_publicados, "corrigidos": 0}
    await _log_execucao("egorealestate_api", resumo, detalhes)
    return resumo
