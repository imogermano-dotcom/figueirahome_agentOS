"""Escrita real em produção (`oportunidades`/`notas`/`tarefas`/`contactos`)
a partir de um batch já mapeado/agrupado por `mapping_todas_colunas.group()`.

Regras da doc (`PIPELINE_SYNC_EGO_SUPABASE_DEV.md` §6/§7), replicadas aqui:
- Nunca sobrescrever um valor existente com null — remover chaves `None` do
  payload antes de cada upsert.
- Deduplicar cada lote pela chave de conflito antes de enviar (evita o erro
  do Postgres "cannot affect row a second time within a single statement").
- Enviar em lotes de 200.
- Preferências (`pref_*`) NUNCA vão no upsert de `oportunidades` — só via
  RPC `bulk_update_prefs`, que por sua vez só aplica se `pref_extraido_em
  IS NULL` (protege extração por IA já feita).
"""
import logging

from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

BATCH = 200

_CONFLICT_KEYS = {
    "oportunidades": ["oportunidade_ref"],
    "notas": ["oportunidade_ref", "nota_texto", "nota_data_raw"],
    "tarefas": ["oportunidade_ref", "tarefa_titulo", "tarefa_due_raw"],
    # `visita_ref_ego` ('VF_2886') é o id da visita no eGO, estável e único.
    # Sem tabela própria as visitas viviam em colunas de `oportunidades`, cuja
    # chave é só `oportunidade_ref` — 5 visitas do mesmo cliente colapsavam
    # numa. Ver migration 0023.
    "visitas": ["visita_ref_ego"],
    "contactos": ["ego_link"],
}


def _strip_none(record: dict) -> dict:
    return {k: v for k, v in record.items() if v is not None and k != "extra"}


def _dedupe(records: list[dict], chave: list[str]) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for r in records:
        k = tuple(r.get(c) for c in chave)
        if any(v is None for v in k):
            continue
        by_key[k] = r  # última ocorrência ganha, igual a imoveis_sync.py
    return list(by_key.values())


def _upsert_tabela(supabase, tabela: str, records: list[dict]) -> int:
    chave = _CONFLICT_KEYS[tabela]
    limpos = [_strip_none(r) for r in records]
    limpos = _dedupe(limpos, chave)
    if not limpos:
        return 0
    on_conflict = ",".join(chave)
    for i in range(0, len(limpos), BATCH):
        supabase.table(tabela).upsert(limpos[i : i + BATCH], on_conflict=on_conflict).execute()
    return len(limpos)


def _upsert_contactos(supabase, records: list[dict]) -> dict:
    """`contactos` tem PK real `(nome, criado_em)` (confirmado ao vivo —
    diferente do que a doc recomendava, `ego_link`). Duas pessoas reais
    diferentes podem partilhar nome+data de criação (visto ao vivo: 2
    "António" distintos) — upsert em lote por `ego_link` não protege dessa
    colisão na OUTRA constraint. Por isso vai registo a registo: sucesso
    conta, colisão de chave (23505) salta e fica no resumo, não aborta o
    resto do lote."""
    chave = _CONFLICT_KEYS["contactos"]
    limpos = _dedupe([_strip_none(r) for r in records], chave)
    ok = 0
    ignorados: list[str] = []
    on_conflict = ",".join(chave)
    for r in limpos:
        try:
            supabase.table("contactos").upsert([r], on_conflict=on_conflict).execute()
            ok += 1
        except APIError as e:
            if e.code == "23505":
                ignorados.append(r.get("nome", "?"))
            else:
                raise
    if ignorados:
        logger.warning(f"contactos: {len(ignorados)} ignorados por colisão de (nome, criado_em): {ignorados}")
    return {"gravados": ok, "ignorados_colisao": len(ignorados)}


def _bulk_update_prefs(supabase, prefs: list[dict]) -> int:
    """RPC `bulk_update_prefs(updates jsonb)` — só actualiza se
    `pref_extraido_em IS NULL` do lado do Postgres (doc §3.7). Assinatura
    exacta não confirmada neste repo (função já existe no Supabase, criada
    fora deste projecto) — se o payload não bater certo, a chamada falha
    com erro claro do Postgrest em vez de escrever em silêncio."""
    limpos = [_strip_none(p) for p in prefs if p.get("oportunidade_ref")]
    if not limpos:
        return 0
    supabase.rpc("bulk_update_prefs", {"updates": limpos}).execute()
    return len(limpos)


def run(supabase, batch: dict) -> dict:
    resumo = {}
    for tabela in ("oportunidades", "notas", "tarefas", "visitas"):
        try:
            resumo[tabela] = _upsert_tabela(supabase, tabela, batch[tabela])
        except Exception:
            logger.exception(f"Falha no upsert de {tabela}")
            resumo[tabela] = f"erro (ver logs) — {len(batch[tabela])} registos não gravados"

    try:
        resumo["contactos"] = _upsert_contactos(supabase, batch["contactos"])
    except Exception:
        logger.exception("Falha no upsert de contactos")
        resumo["contactos"] = f"erro (ver logs) — {len(batch['contactos'])} registos não gravados"

    try:
        resumo["prefs"] = _bulk_update_prefs(supabase, batch["prefs"])
    except Exception:
        logger.exception("Falha no RPC bulk_update_prefs")
        resumo["prefs"] = f"erro (ver logs) — {len(batch['prefs'])} registos não gravados"

    return resumo
