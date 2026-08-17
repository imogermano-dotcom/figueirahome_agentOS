"""Upsert de imóveis vindos do eGO Real Estate para a tabela `imoveis`
(projecto secundário Supabase). Full-sync paginado sempre (ver nota em
`egorealestate.py` sobre o endpoint /Latest estar avariado do lado do eGO).
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

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


# `FeatureTags` é uma lista plana {Tag, Value} — a presença da tag é que conta,
# o Value vem vazio na maioria (ex: PROPERTY_HAS_AC).
#
# Escolher a tag certa importa: `Features` vem agrupado, e o grupo distingue o
# que o imóvel TEM ([Divisões]/[Equipamentos]/[Infraestruturas]) do que há PERTO
# ([Zona Envolvente]). Mapear a tag errada faz o A1 afirmar ao comprador que um
# imóvel tem coisas que não tem. Duas armadilhas medidas ao vivo (2026-08-12):
#   - `SWIMMING_POOLS` (4/54) é "[Zona Envolvente] Piscinas" = há piscinas na
#     zona. A piscina do imóvel é `PROPERTY_HAS_POOL` (2/54).
#   - `PROPERTY_NEAR_GARDENS` (23/54) é "[Zona Envolvente] Espaços Verdes"; o
#     jardim do imóvel é `PROPERTY_HAS_GARDEN`, "[Infraestruturas] Jardim".
#     FH2581 traz as duas ao mesmo tempo — é o caso que prova a distinção.
# `arrecadacao` e `numero` não existem em lado nenhum da Web API.
_FEATURE_BOOLS = {
    "garagem": "PROPERTY_HAS_GARAGE",
    "jardim": "PROPERTY_HAS_GARDEN",
    "estacionamento": "PROPERTY_NUM_PARKING_SPACES",
    "elevador": "PROPERTY_HAS_ELEVATOR",
    "varanda": "PROPERTY_HAS_BALCONY",
    "terraco": "PROPERTY_HAS_TERRACE",
    "ar_condicionado": "PROPERTY_HAS_AC",
    "aquecimento_central": "PROPERTY_HAS_CENTRAL_HEATING",
    "piscina": "PROPERTY_HAS_POOL",
    "vista_mar": "SEA_VIEW",
    "vista_praia": "BEACH_VIEW",
}

# `ExclusiveRegime` é binário (0/1) mas a coluna é texto e tem 4 valores vindos
# do Excel. Nos 53 imóveis que a API devolve o vocabulário bate certo (44/9),
# por isso não há perda; Co-Exclusivo/Concorrência só existem em linhas que a
# API nunca toca.
_EXCLUSIVIDADE = {0: "Regime aberto", 1: "Exclusivo"}


def _feature_tags(p: dict) -> dict[str, str]:
    return {f["Tag"]: (f.get("Value") or "") for f in (p.get("FeatureTags") or []) if f.get("Tag")}


def _angariador(p: dict) -> str | None:
    """Um agente por imóvel, role sempre `Angariador` (ID 4) — confirmado nos 54."""
    for agente in p.get("PropertyAgents") or []:
        if any(r.get("ID") == 4 for r in agente.get("Roles") or []):
            return agente.get("AgentName") or None
    return None


def _data(value: str | None) -> str | None:
    """`CreatedDate`/`LastModified` vêm ISO com hora; as colunas são `date`."""
    return value[:10] if value else None


def _gps(p: dict) -> tuple[float, float] | tuple[None, None]:
    """`GPSLat`/`GPSLon` vêm sempre preenchidos, mas só valem alguma coisa com
    `HasGPSLocation` — sem ele o eGO devolve o centróide da zona. Medido ao vivo
    (2026-08-12): 42 dos 54 imóveis têm o flag a False e partilham 10
    coordenadas, 19 deles no mesmo ponto. Marcá-los no mapa seria inventar uma
    morada que não sabemos."""
    if not p.get("HasGPSLocation"):
        return None, None
    return p.get("GPSLat"), p.get("GPSLon")


def _utc_iso(value: str | None) -> str | None:
    """eGO devolve timestamps sem offset (mas são UTC, per doc oficial)."""
    if not value:
        return None
    return value if value.endswith("Z") or "+" in value[10:] else f"{value}+00:00"


def _map_property(p: dict) -> dict:
    tags = _feature_tags(p)
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

    record = {
        "ego_id": p.get("ID"),
        "imovel_ref": p.get("Reference"),
        "natureza": p.get("Type"),
        "estado": p.get("Condition"),
        "disponibilidade": p.get("Availability"),
        "quartos": _int_or_none(p.get("Rooms")),
        "casas_banho": _int_or_none(p.get("Bathrooms")),
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
        "plantas": [bp["Thumbnail"] for bp in (p.get("BluePrints") or []) if bp.get("Thumbnail")],
        "video_url": next((v["VideoUrl"] for v in (p.get("Videos") or []) if v.get("VideoUrl")), None),
        "panoramic_url": p.get("MainPanoramicUrl") or None,
        "destaque": any(t.get("Name") == "Destaque" for t in (p.get("Tags") or [])),
        "ego_atualizado_em": _utc_iso(p.get("LastModified")),
        "data_criacao": _data(p.get("CreatedDate")),
        "data_alteracao": _data(p.get("LastModified")),
        "exclusividade": _EXCLUSIVIDADE.get(p.get("ExclusiveRegime")),
        "fonte": "egorealestate",
        "disponivel_na_api": True,
        **{col: tag in tags for col, tag in _FEATURE_BOOLS.items()},
    }

    return record


def _map_extras(p: dict) -> dict:
    """Campos que a API só traz para alguns imóveis, mas que a BD já tem
    preenchidos pelo import Excel/CRM (`conservacao`: 6/54 na API contra 42
    linhas na BD).

    Vão FORA do upsert, aplicados linha a linha, e a razão é dura: o PostgREST
    constrói um único `INSERT ... ON CONFLICT` sobre a UNIÃO das chaves de todo
    o lote. Basta um registo trazer `latitude` para a coluna entrar no
    statement, e todos os outros do lote são escritos a NULL — omitir a chave
    não protege nada. Aconteceu ao vivo em 2026-08-12: 40 imóveis publicados
    perderam a coordenada num único sync. Ver `test_upsert_com_chaves_uniformes`.
    """
    tags = _feature_tags(p)
    n_suites = tags.get("PROPERTY_HAS_SUITE") or ""
    # `Floor` só vem em 17/54; a tag `PROPERTY_FLOOR` cobre 19 e nunca diverge
    # do `Floor` quando ambos existem — serve de fallback.
    piso = _int_or_none(p.get("Floor"))
    piso = str(piso) if piso is not None else (tags.get("PROPERTY_FLOOR") or None)
    latitude, longitude = _gps(p)
    extras = {
        "conservacao": tags.get("FEATURE_CONDITION") or None,
        "certificacao_energetica": p.get("EnergyCertification") or None,
        "angariador": _angariador(p),
        "suites": int(n_suites) if n_suites.isdigit() else None,
        "piso": piso,
        "latitude": latitude,
        "longitude": longitude,
    }
    return {k: v for k, v in extras.items() if v is not None}


def _dedup_por_ref(records: list[dict]) -> dict[str, dict]:
    """`imovel_ref` é a PK real da tabela (chave partilhada com o resto do
    sistema); o upsert por `ego_id` colidiria com linhas já existentes por
    referência (ex: entradas manuais que o eGO agora também reporta). O eGO
    ocasionalmente devolve a mesma Reference em 2 propriedades — dado sujo do
    lado deles — e o Postgres não aceita ON CONFLICT duplicado no mesmo batch.

    Desempate pela data de alteração, não pela ordem da lista: a ordem do eGO é
    arbitrária e a cópia velha costuma ser a que ficou por preencher. Medido em
    `FH2460 4D` (2026-08-12) — duas propriedades com a mesma Reference, e a que
    a ordem escolhia não tinha `Floor`, gravando piso 0 num 4.º andar.
    """
    by_ref: dict[str, dict] = {}
    for r in records:
        anterior = by_ref.get(r["imovel_ref"])
        if anterior is None:
            by_ref[r["imovel_ref"]] = r
            continue
        perdedor = min(anterior, r, key=lambda x: x.get("ego_atualizado_em") or "")
        vencedor = anterior if perdedor is r else r
        logger.warning(
            "imovel_ref duplicado no batch eGO: %s (ego_id %s ignorado, fica %s por ser mais recente)",
            r["imovel_ref"], perdedor["ego_id"], vencedor["ego_id"],
        )
        by_ref[r["imovel_ref"]] = vencedor
    return by_ref


# Só erros em que o pedido **não chegou a ser processado**: um socket que o outro
# lado já fechou falha na escrita. Um timeout de leitura fica sem saber se o
# servidor aplicou a escrita, por isso não entra aqui — repeti-lo duplicaria.
_ERROS_DE_LIGACAO = (httpx.RemoteProtocolError, httpx.ConnectError)


async def _run(fn):
    """Corre uma chamada síncrona do PostgREST fora do event loop, com **uma**
    repetição em erro de ligação.

    O cliente Supabase guarda a conexão no pool, e este sync tem trechos longos
    sem lhe tocar: a validação CRM raspa o backoffice inteiro durante ~2,5 min.
    Nesse intervalo o outro lado fecha a conexão, e a chamada seguinte reutiliza
    um socket morto — `RemoteProtocolError: Server disconnected`, visto em
    produção a 2026-08-17 no insert do log, com o sync todo já feito.
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn)
    except _ERROS_DE_LIGACAO as e:
        logger.warning("Ligação ao Supabase caída (%s); a repetir uma vez.", type(e).__name__)
        return await loop.run_in_executor(None, fn)


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


async def _fechar_tarefas_despublicado(refs: list[str]) -> None:
    """Fecha as tarefas "eGO deixou de publicar" cujos imóveis já foram
    resolvidos pela validação CRM. Sem isto acumulam-se — havia 20 pendentes a
    2026-08-14, nenhuma fechada, porque a tarefa é criada automaticamente e só
    se fechava à mão."""
    if not refs:
        return

    def _fechar():
        return (
            get_supabase()
            .table("agente_tarefas")
            .update({"estado": "concluida"})
            .eq("estado", "pendente")
            .like("titulo", f"{_TAREFA_TITULO_PREFIX}%")
            .in_("imovel_ref", refs)
            .execute()
        )

    try:
        await _run(_fechar)
    except Exception:
        logger.exception("Falha a fechar tarefas de despublicação (%s refs)", len(refs))


async def _flag_unpublished(missing_ego_ids: set[int]) -> tuple[int, list[dict], list[str]]:
    """`/v1/Properties/Latest` reporta o ID como alterado, mas `/v1/Properties`
    já não o devolve — a API só devolve imóveis publicados. Não sabemos qual o
    estado real (Por validar / Retirado / Em Prospecção), por isso não
    adivinhamos `disponibilidade`: criamos uma tarefa para o corretor confirmar
    no CRM, uma vez por imóvel. Marcamos sempre `disponivel_na_api=False`
    (independente de já existir tarefa) — é o único facto certo desta pull, e
    a coluna `publicado` (generated) depende dele para não ficar `true`
    indevidamente enquanto `disponibilidade` ainda não foi corrigida pelo CRM."""
    if not missing_ego_ids:
        return 0, [], []

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
        return 0, [], []

    def _marcar_nao_visto():
        return get_supabase().table("imoveis").update({"disponivel_na_api": False}).in_("imovel_ref", refs).execute()

    await _run(_marcar_nao_visto)

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
        # Sem tarefa nova, mas os refs interessam ao chamador na mesma: e sobre
        # eles que a validacao CRM tem de correr.
        return 0, [], refs

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
    return len(novos), detalhes, refs


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


async def validar_disponibilidade_crm(
    apenas_refs: set[str] | None = None,
) -> tuple[int, list[dict]]:
    """Cruza o backoffice autenticado do eGO (visibilidade total, incl.
    imóveis nunca publicados) com a tabela `imoveis`. Ao contrário da Web API
    pública, aqui o valor de `disponibilidade` é conhecido com certeza, por
    isso corrige-se directamente em vez de só sinalizar. Três sub-casos:
    1) CRM diz Disponível, sem linha local → cria linha nova (fetch_detail).
    2) CRM diz X, linha local diz outra coisa → corrige directamente.
    3) Linha local diz Disponível, CRM não a lista como Disponível → relê o
       estado real via fetch_detail (se soubermos o ego_id) e corrige.

    `apenas_refs` restringe **tudo** a esse conjunto e desliga o Caso 1. É o
    modo que o sync da Web API usa para os imóveis que a API deixou de devolver:
    sobre esses a API não tem opinião nenhuma, por isso o CRM pode corrigir sem
    contrariar nada — que era exactamente a razão de a validação completa ter
    saído do cron (sobrepunha estados que a API pública já confirmava, caso
    `FH2483_A`; ver `docs/decisoes.md`).

    Restringir tem de valer para as consultas locais também: o Caso 3 considera
    "stale" tudo o que diga Disponível e não esteja na lista CRM-Disponível, e
    com `crm_items` filtrado sem filtrar o lado local marcaria os 53 publicados
    como stale de uma vez.
    """
    if not settings.egorealestate_crm_username or not settings.egorealestate_crm_password:
        return 0, []

    detalhes: list[dict] = []

    async with egorealestate_crm.authenticated_client() as client:
        await egorealestate_crm._login(client)
        crm_items = await egorealestate_crm.fetch_all(client)
        if apenas_refs is not None:
            crm_items = [i for i in crm_items if i.get("imovel_ref") in apenas_refs]
        elif not crm_items:
            # Sem escopo, lista vazia é sinal de o backoffice ter falhado, não
            # de não haver imóveis — abortar antes de o Caso 3 marcar tudo.
            # Com escopo, vazio é normal: um imóvel vendido não aparece em
            # `fetch_all` (`_STATUS_CODES` não inclui Vendido) e é precisamente
            # o Caso 3, via `fetch_detail`, que descobre o estado real.
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
        # Desligado quando há escopo: essa chamada existe para corrigir o que já
        # existe, não para importar imóveis novos pela porta das traseiras.
        criados = []
        for item in crm_items if apenas_refs is None else []:
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
            q = (
                get_supabase()
                .table("imoveis")
                .select("imovel_ref,ego_id")
                .eq("disponibilidade", "Disponível")
            )
            if apenas_refs is not None:
                q = q.in_("imovel_ref", list(apenas_refs))
            return q.execute()

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
    """O log é o registo, não o trabalho — se falhar, o sync não passa a ter
    falhado.

    A 2026-08-17 um `Server disconnected` aqui devolveu **502** ao cron com o
    upsert e a validação CRM já feitos: a Action ficou vermelha por um sync que
    correu bem. O preço de engolir é o painel poder ficar sem a linha de uma
    execução que aconteceu — mas isso lê-se nos logs do Fly, enquanto um 502
    manda investigar uma avaria que não existe.
    """
    def _insert():
        return get_supabase().table("agente_sync_log").insert({
            "tipo": tipo, "resumo": resumo, "detalhes": detalhes,
        }).execute()

    try:
        await _run(_insert)
    except Exception:
        logger.exception("Falha a gravar o log de %s — o sync em si correu.", tipo)


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
    nao_publicados, det_nao_publicados, refs_despublicados = await _flag_unpublished(missing)
    detalhes.extend(det_nao_publicados)

    # A validação CRM destes refs corre no FIM, depois do upsert — ver o bloco
    # no fecho desta função. Aqui só se sabe quais são.
    corrigidos = 0

    if not properties:
        resumo = {"criados": 0, "atualizados": 0, "erros": 0, "nao_publicados": nao_publicados, "corrigidos": corrigidos}
        await _log_execucao("egorealestate_api", resumo, detalhes)
        return resumo

    now_iso = datetime.now(timezone.utc).isoformat()
    records = []
    extras_por_ego_id: dict[int, dict] = {}
    erros = 0
    for p in properties:
        try:
            record = _map_property(p)
            if not record["imovel_ref"]:
                raise ValueError("propriedade eGO sem Reference")
            record["ego_atualizado_em"] = record["ego_atualizado_em"] or now_iso
            records.append(record)
            extras_por_ego_id[record["ego_id"]] = _map_extras(p)
        except Exception:
            logger.exception("Falha a mapear propriedade eGO %s", p.get("ID"))
            erros += 1

    by_ref = _dedup_por_ref(records)
    records = list(by_ref.values())

    extras_por_ref = {ref: extras_por_ego_id.get(r["ego_id"], {}) for ref, r in by_ref.items()}
    refs = list(by_ref)
    existentes = await _existing_refs(refs)

    def _upsert():
        return get_supabase().table("imoveis").upsert(records, on_conflict="imovel_ref").execute()

    await _run(_upsert)

    # Os esparsos vão depois e um a um: dentro do lote, uma chave presente em
    # qualquer registo torna-se coluna do statement e escreve NULL em todos os
    # outros. Ver `_map_extras`.
    # ponytail: um UPDATE por imóvel (~53/dia). Se o portefólio crescer uma
    # ordem de grandeza, agrupar por conjunto de chaves e mandar um upsert por
    # grupo — cada grupo tem chaves uniformes, que é a condição que falta aqui.
    def _aplicar_extras():
        sb = get_supabase()
        for ref, extras in extras_por_ref.items():
            if extras:
                sb.table("imoveis").update(extras).eq("imovel_ref", ref).execute()

    await _run(_aplicar_extras)

    # A Web API só devolve publicados: a partir do momento em que um imóvel sai
    # dela, deixa de haver fonte automática sobre o que lhe aconteceu — se for
    # vendido a seguir, nada o traz ao Supabase. Só o backoffice o sabe.
    #
    # Correr a validação CRM **restrita a estes refs** fecha isso sem repetir o
    # erro que a tirou do cron: ela sobrepunha estados que a API pública já
    # tinha confirmado (caso FH2483_A), e aqui a API não tem opinião nenhuma
    # sobre estes imóveis, por definição.
    #
    # ⚠️ **Depois do upsert, nunca antes.** É lenta — `fetch_all` raspa o
    # backoffice inteiro antes de o escopo filtrar o que quer que seja — e com
    # ela à frente estourou o `--max-time` do cron a 2026-08-16/17: o curl
    # desligava, o handler era cancelado, e o upsert dos imóveis nunca chegava a
    # correr. Dois dias sem sync e sem log. O `try/except` protege de
    # excepções; não protegia de o cliente desistir. A ordem é que protege.
    if refs_despublicados:
        try:
            corrigidos, det_crm = await validar_disponibilidade_crm(set(refs_despublicados))
            detalhes.extend(det_crm)
            resolvidos = [d["imovel_ref"] for d in det_crm if d.get("tipo") == "corrigido_crm"]
            await _fechar_tarefas_despublicado(resolvidos)
        except Exception:
            # O sync da Web API é a parte que funciona; uma falha de login ou de
            # scraping do backoffice não a pode derrubar. Fica o aviso e a
            # tarefa que `_flag_unpublished` já criou.
            logger.exception(
                "Validação CRM dos despublicados falhou (%s refs) — sync da API segue.",
                len(refs_despublicados),
            )

    criados = sum(1 for r in records if r["imovel_ref"] not in existentes)
    atualizados = len(records) - criados
    detalhes.extend(
        {"imovel_ref": r["imovel_ref"], "tipo": "criado" if r["imovel_ref"] not in existentes else "atualizado"}
        for r in records
    )
    resumo = {"criados": criados, "atualizados": atualizados, "erros": erros, "nao_publicados": nao_publicados, "corrigidos": corrigidos}
    await _log_execucao("egorealestate_api", resumo, detalhes)
    return resumo
