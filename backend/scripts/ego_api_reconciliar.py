"""Compara as oportunidades ativas do eGO (API) com `oportunidades` no Supabase. SÓ LEITURA, sem PII (referências e contagens).

    python scripts/ego_api_reconciliar.py            # resumo
    python scripts/ego_api_reconciliar.py --refs     # + lista das referências em falta

Base da fase A5 de `docs/fases/ego-api-substituir-scrapers-plano.md`: mede o que o sync por relatório (janela de 48 h) deixou por gravar.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ESTADO = {0: "Ativa", 1: "Ativa", 2: "Ganha", 3: "Perdida"}  # leadStage da API → oportunidade_estado (0 = «Criada», que gravamos como Ativa)


def comparar(api: list[dict], db: dict[str, str | None]) -> dict:
    """`api`: linhas de `ListOpportunityByPage` (ativas); `db`: `{oportunidade_ref: oportunidade_estado}`."""
    em_falta = sorted((o["name"] for o in api if o["name"] not in db), key=lambda r: r)
    dia = {o["name"]: (o.get("createDate") or "")[:10] for o in api}
    estado_diferente = [
        o["name"] for o in api
        if o["name"] in db and db[o["name"]] != _ESTADO.get(o.get("leadStage"), "?")
    ]
    nomes = {o["name"] for o in api}
    return {
        "api_ativas": len(api),
        "em_falta_no_supabase": len(em_falta),
        "em_falta_por_dia_de_criacao": dict(sorted(Counter(dia[r] for r in em_falta).items())),
        "estado_diferente": len(estado_diferente),
        "estado_diferente_refs": sorted(estado_diferente),
        "ativas_no_supabase_fora_da_lista": sum(1 for r, e in db.items() if e == "Ativa" and r not in nomes),
        "refs_em_falta": em_falta,
    }


def _ler_db() -> dict[str, str | None]:
    from app.db.supabase_client import get_supabase
    sb, db, inicio = get_supabase(), {}, 0
    while True:  # ordenado: sem `order` a paginação do PostgREST salta e repete linhas
        lote = (sb.table("oportunidades").select("oportunidade_ref,oportunidade_estado")
                .order("oportunidade_ref").range(inicio, inicio + 999).execute().data)
        db.update({x["oportunidade_ref"]: x["oportunidade_estado"] for x in lote})
        inicio += 1000
        if len(lote) < 1000:
            return db


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from app.integrations import ego_api
    r = comparar(ego_api.oportunidades_ativas(), _ler_db())
    refs = r.pop("refs_em_falta")
    for k, v in r.items():
        print(f"{k}: {v}")
    if "--refs" in sys.argv:
        print("refs_em_falta:", ", ".join(refs))
