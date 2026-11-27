"""Oportunidades da API do eGO vs `oportunidades` gravadas pelo relatório (P3 de `docs/fases/api-a-substituir-scraper-acelerado-plano.md`).
SÓ LEITURA, sem PII: só contagens por coluna, motivos e as tabelas de códigos (portal), que são categorias da agência.

    python scripts/comparar_oportunidades_api_relatorio.py            # lista de ativas + etapas + imóveis, sem preferências
    python scripts/comparar_oportunidades_api_relatorio.py --prefs 150  # compara também as preferências de 150 oportunidades
    python scripts/comparar_oportunidades_api_relatorio.py --teste

Por coluna diz quantas são iguais e, nas que não são, se é «BD vazia» (a API sabe mais), «API vazia» ou «diferente». Mede também as oportunidades
**atrasadas** (a BD tem um `ego_editado_em` anterior ao `alterDate` da API: o relatório ainda não viu a última edição).
Critério para passar a escrever pela API: cada coluna ≥ 99 % iguais nos pares, com as divergências explicadas.
"""

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations import ego_oportunidades as eo  # noqa: E402

_ESTADO = {0: "Ativa", 1: "Ativa", 2: "Ganha", 3: "Perdida"}  # leadStage; o 0 era «Criada» e o scraper também o guarda como Ativa


def _n(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip().lower()


def _data(v) -> str | None:
    return (str(v)[:10] or None) if v else None


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def valores_da_api(o: dict, etapa: str | None, imovel: dict | None, utilizadores: dict[int, str]) -> dict:
    """Coluna da BD → valor que a API dá (já no formato da BD). O que a API não dá fica de fora."""
    pt = eo._pt
    v = {
        "oportunidade_estado": _ESTADO.get(o.get("leadStage")), "tipo_oportunidade": eo._TIPO_OPORTUNIDADE.get((o.get("masterLeadType") or {}).get("id")),
        "tipo_pedido": eo._TIPO_PEDIDO.get(o.get("leadTypeId")), "origem": pt(o.get("leadOrigin")), "sub_origem": pt(o.get("leadSubOrigin")),
        "responsavel": utilizadores.get(o.get("assignToSecurityUserId")), "cliente_nome": o.get("title"), "cliente_email": o.get("email"),
        "cliente_telefone": o.get("phone"), "ego_lead_id": o.get("id"), "ego_data_criacao": _data(o.get("createDate")),
        "ego_editado_em": _data(o.get("alterDate")), "estado_fechado_em": _data(o.get("closedDate")), "imovel_ref": o.get("realestateReference"),
        "etapa_atual": etapa, "valor_negocio": _num(o.get("businessFinalPrice")), "data_escritura": _data(o.get("businessExecutionDate")),
        "ponto_situacao": o.get("situationPoint"), "ponto_situacao_alterado_em": _data(o.get("situationPointAlterDate")) if o.get("situationPoint") else None,
    }
    if imovel:
        v.update({"imovel_natureza": imovel.get("natureza"), "imovel_concelho": imovel.get("concelho"), "imovel_freguesia": imovel.get("freguesia"),
                  "imovel_proprietario": imovel.get("proprietario"), "imovel_venda": _num(imovel.get("venda_preco"))})
    return v


def _igual(col: str, a, b) -> bool:
    if col in ("valor_negocio", "imovel_venda"):
        return _num(a) == _num(b)
    if col.endswith("_em") or col in ("ego_data_criacao", "data_escritura"):
        return _data(a) == _data(b)
    return _n(a) == _n(b)


def comparar(ativas: list[dict], bd: dict[str, dict], etapas: dict[str, str], imoveis: dict[str, dict], utilizadores: dict[int, str]) -> dict:
    r = {"ativas": len(ativas), "so_api": 0, "col": defaultdict(Counter), "atrasadas": 0, "portal": defaultdict(Counter)}
    for o in ativas:
        ref = o.get("name")
        linha = bd.get(ref)
        if not ref:
            continue
        if linha is None:
            r["so_api"] += 1
            continue
        api = valores_da_api(o, etapas.get(ref), imoveis.get(o.get("realestateReference")), utilizadores)
        if _data(linha.get("ego_editado_em")) and _data(o.get("alterDate")) and _data(linha["ego_editado_em"]) < _data(o["alterDate"]):
            r["atrasadas"] += 1
        for col, va in api.items():
            vb = linha.get(col)
            if va in (None, "") and vb in (None, ""):
                continue
            c = r["col"][col]
            c["igual" if _igual(col, va, vb) else "BD vazia" if vb in (None, "") else "API vazia" if va in (None, "") else "diferente"] += 1
        if o.get("portalId") and linha.get("portal"):
            r["portal"][o["portalId"]][linha["portal"]] += 1
    return r


def _imprimir(r: dict) -> None:
    print(f"ativas na API: {r['ativas']}; só na API (sem linha na BD): {r['so_api']}; atrasadas (a BD não viu a última edição): {r['atrasadas']}")
    print(f"{'coluna':30}{'igual':>8}{'BD vazia':>10}{'API vazia':>11}{'diferente':>11}   % igual")
    for col, c in sorted(r["col"].items()):
        t = sum(c.values())
        print(f"{col:30}{c['igual']:8}{c['BD vazia']:10}{c['API vazia']:11}{c['diferente']:11}   {100 * c['igual'] / t:5.1f}")
    print("portal (portalId -> nome na BD):", {k: dict(v) for k, v in sorted(r["portal"].items())})


def _com_espera(f):
    for _ in range(8):
        try:
            return f()
        except Exception as e:
            if "429" not in str(e):
                raise
            time.sleep(60)
    raise RuntimeError("429 persistente")


def _prefs(ativas: list[dict], bd: dict[str, dict], n: int) -> None:
    from app.integrations import ego_api

    nat, est = ego_api.naturezas_de_imovel(), ego_api.estados_de_imovel()
    locais: dict[int, str] = {}

    def local_de(i):
        if i not in locais:
            nome, nivel = ego_api.localizacao(i)
            locais[i] = nome if nome and (nivel or 0) >= 3 else ""
        return locais[i]

    c = defaultdict(Counter)
    amostra = [o for o in ativas if o.get("name") in bd][:n]
    for o in amostra:
        p = _com_espera(lambda: ego_api.preferencias(o["id"]))
        if not p:
            c["(sem preferências no eGO)"]["total"] += 1
            continue
        linha = bd[o["name"]]
        ia = "com IA" if linha.get("pref_extraido_em") else "sem IA"
        for col, va in eo.pref_de_api(p, nat, est, local_de).items():
            vb = linha.get(col)
            c[f"{col} ({ia})"]["igual" if _igual(col, va, vb) else "BD vazia" if vb in (None, "") else "diferente"] += 1
    print(f"\npreferências, amostra de {len(amostra)} oportunidades:")
    for col, x in sorted(c.items()):
        print(f"  {col:44} {dict(x)}")


def main() -> None:
    from app.db.supabase_client import get_supabase
    from app.integrations import ego_api

    ap = argparse.ArgumentParser()
    ap.add_argument("--prefs", type=int, default=0)
    a = ap.parse_args()
    ativas = _com_espera(ego_api.oportunidades_ativas)
    etapas = _com_espera(ego_api.etapas_ativas)
    sb, bd, ini = get_supabase(), {}, 0
    refs = {o["name"] for o in ativas if o.get("name")}
    while True:
        lote = sb.table("oportunidades").select("*").order("oportunidade_ref").range(ini, ini + 999).execute().data
        bd |= {x["oportunidade_ref"]: x for x in lote if x["oportunidade_ref"] in refs}
        ini += 1000
        if len(lote) < 1000:
            break
    imoveis, rs = {}, sorted({o["realestateReference"] for o in ativas if o.get("realestateReference")})
    for i in range(0, len(rs), 300):
        imoveis |= {x["imovel_ref"]: x for x in sb.table("imoveis").select("imovel_ref,natureza,concelho,freguesia,proprietario,venda_preco").in_("imovel_ref", rs[i:i + 300]).execute().data}
    _imprimir(comparar(ativas, bd, etapas, imoveis, ego_api.utilizadores()))
    if a.prefs:
        _prefs(ativas, bd, a.prefs)


def demo() -> None:
    o = {"name": "VEN_1", "id": 1, "leadStage": 1, "masterLeadType": {"id": 2}, "leadTypeId": 4, "title": "Pessoa Teste", "email": "x@example.com", "phone": "912345678",
         "createDate": "2026-11-20T10:00:00", "alterDate": "2026-11-25T10:00:00", "realestateReference": "FH0001", "assignToSecurityUserId": 3,
         "leadOrigin": {"nameMls": {"PT-PT": "Outros"}}, "leadSubOrigin": {"nameMls": {"PT-PT": "Facebook campanha"}}, "businessFinalPrice": 100000.0, "portalId": 700,
         "situationPoint": "Visita marcada", "situationPointAlterDate": "2026-11-25T09:00:00"}
    bd = {"VEN_1": {"oportunidade_ref": "VEN_1", "oportunidade_estado": "Ativa", "tipo_oportunidade": "Venda", "tipo_pedido": "Pedido de Informação",
                    "cliente_nome": "Pessoa Teste", "ego_lead_id": 1, "ego_data_criacao": "2026-11-20", "ego_editado_em": "2026-11-23", "imovel_ref": "FH0001",
                    "origem": "Outros", "sub_origem": "Outra", "responsavel": None, "valor_negocio": 100000, "portal": "Idealista PT", "imovel_concelho": "Figueira da Foz"}}
    r = comparar([o, {"name": "VEN_2", "id": 2}], bd, {"VEN_1": "4-Qualificação"}, {"FH0001": {"concelho": "Figueira da Foz"}}, {3: "Consultora Teste"})
    c = r["col"]
    assert r["so_api"] == 1 and r["atrasadas"] == 1, "VEN_2 não tem linha; VEN_1 foi editada depois de a BD a ver"
    assert c["oportunidade_estado"]["igual"] == 1 and c["valor_negocio"]["igual"] == 1 and c["imovel_concelho"]["igual"] == 1
    assert c["sub_origem"]["diferente"] == 1 and c["responsavel"]["BD vazia"] == 1 and c["etapa_atual"]["BD vazia"] == 1 and c["ponto_situacao"]["BD vazia"] == 1
    assert r["portal"] == {700: Counter({"Idealista PT": 1})}
    print("comparar oportunidades OK")


if __name__ == "__main__":
    demo() if "--teste" in sys.argv else main()
