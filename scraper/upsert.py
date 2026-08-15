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


# Erros do Postgres que significam "este registo não dá, os outros dão" — saltar
# e continuar, nunca abortar o lote:
#
# 23505  chave duplicada. `contactos` tem PK real `(nome, criado_em)` (confirmado
#        ao vivo, diferente do que a doc recomendava, `ego_link`), e duas pessoas
#        reais podem partilhar nome + data de criação — visto ao vivo, 2
#        "António" distintos. O upsert por `ego_link` não protege dessa colisão
#        na OUTRA constraint.
#
# 23503  chave estrangeira. `leads_angariacao` referencia `contactos` por
#        `fk_contacto`, e o upsert por `ego_link` faz UPDATE das colunas da PK
#        quando o nome ou a data mudam do lado do eGO. Se houver uma lead a
#        apontar para o valor antigo, o Postgres recusa:
#          Key (nome, criado_em)=(José de Matos, 2026-06-30) is still referenced
#        Antes só o 23505 era apanhado, e este rebentava a função a meio: um
#        registo assim matava todos os que vinham a seguir no lote, todos os
#        dias, desde que existe a FK. Medido a 2026-08-15: 211 registos dados
#        como não gravados numa corrida — número que, ainda por cima, era o
#        total de entrada e não o que realmente falhou.
_ERROS_POR_REGISTO = {
    "23505": "colisão de (nome, criado_em)",
    "23503": "referenciado por leads_angariacao (FK)",
}


def _upsert_contactos(supabase, records: list[dict]) -> dict:
    """Registo a registo: sucesso conta, registo impossível salta e fica no
    resumo. O que não pode acontecer é um registo mau levar o lote atrás."""
    chave = _CONFLICT_KEYS["contactos"]
    limpos = _dedupe([_strip_none(r) for r in records], chave)
    ok = 0
    ignorados: dict[str, list[str]] = {}
    on_conflict = ",".join(chave)
    for r in limpos:
        try:
            supabase.table("contactos").upsert([r], on_conflict=on_conflict).execute()
            ok += 1
        except APIError as e:
            motivo = _ERROS_POR_REGISTO.get(e.code)
            if not motivo:
                raise
            ignorados.setdefault(motivo, []).append(r.get("nome", "?"))

    for motivo, nomes in ignorados.items():
        logger.warning("contactos: %d ignorados — %s: %s", len(nomes), motivo, nomes)

    # Contagens reais. O resumo antigo dizia "N não gravados" com N = total de
    # entrada, mesmo tendo gravado a maior parte antes de rebentar.
    return {
        "gravados": ok,
        "ignorados": sum(len(n) for n in ignorados.values()),
        "por_motivo": {m: len(n) for m, n in ignorados.items()},
    }


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


def demo() -> None:
    """Auto-verificação do upsert de contactos.  `python upsert.py` de `scraper/`

    O caso real de 2026-08-15: um registo com FK a apontar-lhe abortava o lote
    inteiro e o resumo dava por não gravados registos que tinham sido gravados.
    """
    class _Tabela:
        def __init__(self, falhas):
            self.falhas = falhas

        def upsert(self, registos, on_conflict=None):
            self.registo = registos[0]
            return self

        def execute(self):
            codigo = self.falhas.get(self.registo["nome"])
            if codigo:
                raise APIError({"message": "erro simulado", "code": codigo})
            return None

    def _supabase(falhas):
        return type("S", (), {"table": lambda s, n: _Tabela(falhas)})()

    registos = [{"ego_link": f"L{i}", "nome": n} for i, n in enumerate(
        ["Ana", "José de Matos", "Bruno", "António", "Carla"])]

    # José dá FK (23503) e António dá chave duplicada (23505). Os outros três
    # têm de ser gravados — antes, o José matava o Bruno, o António e a Carla.
    r = _upsert_contactos(_supabase({"José de Matos": "23503", "António": "23505"}), registos)
    assert r["gravados"] == 3, r
    assert r["ignorados"] == 2, r
    assert r["por_motivo"] == {
        "referenciado por leads_angariacao (FK)": 1,
        "colisão de (nome, criado_em)": 1,
    }, r

    # Um erro que não seja "este registo não dá" continua a rebentar: não vale
    # a pena engolir uma falha de rede ou de permissões registo a registo.
    try:
        _upsert_contactos(_supabase({"Ana": "42501"}), registos)
    except APIError:
        pass
    else:
        raise AssertionError("erro desconhecido devia ter rebentado")

    print("upsert OK")


if __name__ == "__main__":
    demo()
