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


def _nome(x) -> str | None:
    """Texto PT de um campo multilíngua da API (`{'name': {'PT-PT': ..}}`, `nameMls`, ou `name` simples)."""
    if not isinstance(x, dict):
        return x or None
    for k in ("nameMls", "name"):
        v = x.get(k)
        if isinstance(v, dict):
            return v.get("PT-PT") or next(iter(v.values()), None)
        if v:
            return v
    return None


def linha_de_oportunidade(o: dict) -> dict:
    """Colunas de `oportunidades` que a lista da API dá diretamente (plano, «Mapa de campos»). Chaves sem valor ficam de fora
    (a escrita é linha a linha, mas assim nunca se grava vazio por cima de dado nosso). Sem `contacto_id` (só por RPC) e sem
    `pref_*`/`xlsx_*`: preenchem-se quando o sync por relatório apanhar a oportunidade numa edição."""
    criada, editada = (o.get("createDate") or "")[:10], (o.get("alterDate") or "")[:10]
    r = {
        "oportunidade_ref": o["name"],
        "oportunidade_estado": _ESTADO.get(o.get("leadStage")),
        # o enum da BD só tem «Angariação» (o relatório normaliza «Angariação III (em Comercialização)» e afins)
        "tipo_oportunidade": (_nome(o.get("masterLeadType")) or "").replace("Angariação III (em Comercialização)", "Angariação"),
        "tipo_pedido": _nome(o.get("leadType")),
        "origem": _nome(o.get("leadOrigin")),
        "sub_origem": _nome(o.get("leadSubOrigin")),
        "cliente_nome": o.get("title"),
        "cliente_telefone": o.get("phone"),
        "cliente_email": o.get("email"),
        "imovel_ref": o.get("realestateReference"),
        "responsavel": ", ".join(o.get("assignToSecurityUserNames") or []),
        "data_criacao_iso": criada,
        "ego_data_criacao": criada,
        "ego_editado_em": editada,
        "url": f"https://admin.egorealestate.com/egocore/Leads/{o['id']}",
        "origem_lista": "todas_as_colunas",
        "agencia": "FIGUEIRAHOME",
    }
    return {k: v for k, v in r.items() if v not in (None, "")}


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


def gravar(api: list[dict], db: dict[str, str | None]) -> dict:
    """INSERT linha a linha das que faltam no Supabase (nunca upsert: não pisa o que o sync por relatório gravar entretanto).
    Regista o resumo em `agente_sync_log` para se poder desfazer. Não corrige estados divergentes (pedido à parte)."""
    from app.db.supabase_client import get_supabase
    sb = get_supabase()
    r = {"inseridas": [], "erros": {}}
    for o in api:
        if o["name"] in db:
            continue
        try:
            sb.table("oportunidades").insert(linha_de_oportunidade(o)).execute()
            r["inseridas"].append(o["name"])
        except Exception as e:
            r["erros"][o["name"]] = repr(e)[:200]
    sb.table("agente_sync_log").insert({"tipo": "egorealestate_oportunidades_api", "origem": "manual", "resumo": r}).execute()
    return r


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from app.integrations import ego_api
    api, db = ego_api.oportunidades_ativas(), _ler_db()
    if "--gravar" in sys.argv:
        res = gravar(api, db)
        print(len(res["inseridas"]), "inseridas;", len(res["erros"]), "erros", res["erros"])
        sys.exit()
    r = comparar(api, db)
    refs = r.pop("refs_em_falta")
    for k, v in r.items():
        print(f"{k}: {v}")
    if "--linhas" in sys.argv:  # dry-run das linhas a gravar, sem o nome do cliente
        db = _ler_db()
        api = ego_api.oportunidades_ativas()
        for o in api:
            if o["name"] in db:
                continue
            l = linha_de_oportunidade(o)
            print(l["oportunidade_ref"], {k: v for k, v in l.items() if k not in ("oportunidade_ref", "cliente_nome", "cliente_telefone", "cliente_email", "url", "agencia", "origem_lista", "ego_data_criacao")},
                  "tel" if l.get("cliente_telefone") else "-", "email" if l.get("cliente_email") else "-")
    if "--refs" in sys.argv:
        print("refs_em_falta:", ", ".join(refs))
