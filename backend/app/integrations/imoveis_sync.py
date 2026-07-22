"""Upsert de imóveis vindos do eGO Real Estate para a tabela `imoveis`
(projecto secundário Supabase). Dedup por ego_id; cursor incremental é o
próprio max(ego_atualizado_em) já gravado — sem tabela de estado extra.
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


async def _last_synced_at() -> datetime | None:
    def _fetch():
        return (
            get_supabase()
            .table("imoveis")
            .select("ego_atualizado_em")
            .eq("fonte", "egorealestate")
            .order("ego_atualizado_em", desc=True)
            .limit(1)
            .execute()
        )

    resp = await _run(_fetch)
    valor = resp.data[0]["ego_atualizado_em"] if resp.data else None
    return datetime.fromisoformat(valor) if valor else None


async def _existing_refs(refs: list[str]) -> set[str]:
    def _fetch():
        return get_supabase().table("imoveis").select("imovel_ref").in_("imovel_ref", refs).execute()

    resp = await _run(_fetch)
    return {r["imovel_ref"] for r in resp.data}


_TAREFA_TITULO_PREFIX = "eGO deixou de publicar"


async def _flag_unpublished(missing_ego_ids: set[int]) -> int:
    """`/v1/Properties/Latest` reporta o ID como alterado, mas `/v1/Properties`
    já não o devolve — a API só devolve imóveis publicados. Não sabemos qual o
    estado real (Por validar / Retirado / Em Prospecção), por isso não
    adivinhamos `disponibilidade`: criamos uma tarefa para o corretor confirmar
    no CRM, uma vez por imóvel."""
    if not missing_ego_ids:
        return 0

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
        return 0

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
        return 0

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
    return len(novos)


async def validar_disponibilidade_crm() -> int:
    """Cruza o backoffice autenticado do eGO (visibilidade total, incl.
    imóveis nunca publicados) com a tabela `imoveis`. Ao contrário da Web API
    pública, aqui o valor de `disponibilidade` é conhecido com certeza, por
    isso corrige-se directamente em vez de só sinalizar. Corrige também
    `ego_id`/`fonte` para linhas que nunca tinham sido ligadas ao eGO."""
    if not settings.egorealestate_crm_username or not settings.egorealestate_crm_password:
        return 0

    crm_items = await egorealestate_crm.fetch_all()
    if not crm_items:
        return 0

    # O eGO por vezes devolve a mesma Reference em 2 propriedades distintas
    # (mesmo problema já conhecido do upsert da Web API, ver sync_egorealestate)
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
        if muda_ego_id:
            update["ego_id"] = item["ego_id"]
        if muda_fonte:
            update["fonte"] = "egorealestate"
        updates.append(update)

    if not updates:
        return 0

    def _apply():
        for u in updates:
            get_supabase().table("imoveis").update(u).eq("imovel_ref", u["imovel_ref"]).execute()

    await _run(_apply)
    return len(updates)


async def sync_egorealestate() -> dict:
    if not settings.egorealestate_api_key:
        raise RuntimeError("EGOREALESTATE_API_KEY não configurada.")

    cursor = await _last_synced_at()
    nao_publicados = 0

    if cursor is None:
        # Primeiro sync — sem cursor, importa o portefólio completo paginado.
        properties: list[dict] = []
        page = 1
        while True:
            batch, total = await egorealestate.get_properties_page(page, PAGE_SIZE)
            properties.extend(batch)
            if not batch or len(properties) >= total:
                break
            page += 1
    else:
        latest = await egorealestate.get_latest(cursor)
        ids = [item["ID"] for item in latest if item.get("ID")]
        properties = await egorealestate.get_properties_by_ids(ids) if ids else []
        # /v1/Properties só devolve imóveis publicados — um ID que o Latest
        # reportou mas que não voltou aqui foi despublicado (estado real
        # desconhecido); sinalizar em vez de deixar o registo antigo por actualizar.
        missing = set(ids) - {p.get("ID") for p in properties}
        nao_publicados = await _flag_unpublished(missing)

    if not properties:
        corrigidos = await validar_disponibilidade_crm()
        return {"criados": 0, "atualizados": 0, "erros": 0, "nao_publicados": nao_publicados, "corrigidos": corrigidos}

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
    corrigidos = await validar_disponibilidade_crm()
    return {"criados": criados, "atualizados": atualizados, "erros": erros, "nao_publicados": nao_publicados, "corrigidos": corrigidos}
