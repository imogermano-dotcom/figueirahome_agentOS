"""Visitas da API do eGO vs `visitas` gravadas pelo relatório (P2 do plano acelerado). SÓ LEITURA, sem PII: só contagens e as
tabelas de códigos (interesse, pontos positivos/negativos, sobre o negócio), que são categorias da agência e não dados de pessoas.

    python scripts/comparar_visitas_api_relatorio.py
    python scripts/comparar_visitas_api_relatorio.py --teste

Critério: API ⊇ BD nas oportunidades ativas e cada coluna ≥ 99 % igual nos pares, com as divergências explicadas.
"""

import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _n(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def _nomes(texto: str | None) -> list[str]:
    return [x.strip() for x in (texto or "").split(",") if x.strip()]


def aprender(pares: list[tuple[list[int], str | None]]) -> tuple[dict[int, str], Counter]:
    """id → nome a partir de pares (lista de ids da API, texto «A, B» da BD). Parte dos casos de 1 id = 1 nome; depois resolve por exclusão
    os de N ids com N nomes onde N-1 já são conhecidos. Devolve também o balanço (ids resolvidos e ambíguos)."""
    mapa: dict[int, Counter] = defaultdict(Counter)
    for ids, texto in pares:
        nomes = _nomes(texto)
        if len(ids) == 1 and len(nomes) == 1:
            mapa[ids[0]][nomes[0]] += 1
    certo = {i: c.most_common(1)[0][0] for i, c in mapa.items()}
    balanco = Counter(ambiguos=sum(1 for c in mapa.values() if len(c) > 1))
    for _ in range(3):
        for ids, texto in pares:
            nomes = _nomes(texto)
            if len(ids) == len(nomes) > 1:
                falta = [i for i in ids if i not in certo]
                livres = [x for x in nomes if x not in {certo.get(i) for i in ids}]
                if len(falta) == 1 and len(livres) == 1:
                    certo[falta[0]] = livres[0]
    balanco["ids_resolvidos"] = len(certo)
    return certo, balanco


def _ids(v, campo: str) -> list[int]:
    x = v.get(campo)
    if campo == "interested":
        return [x] if isinstance(x, int) and x else []
    return list(x or [])


def comparar(api: list[dict], bd: list[dict], nome_de_lead: dict[int, str], ref_de_imovel: dict[int, str], utilizadores: dict[int, str],
             resp_da_oportunidade: dict[str, str] | None = None) -> dict:
    """Ids sem nome na tabela ignoram-se (o relatório também os omite: são opções que já não aparecem). Responsável da visita = o utilizador
    da visita e, se já saiu do eGO, o responsável da oportunidade (96 % contra o relatório)."""
    por_ref = {v["visitReference"]: v for v in api if v.get("visitReference")}
    bd_por_ref = {x["visita_ref_ego"]: x for x in bd}
    r = {"api": len(por_ref), "bd": len(bd_por_ref), "so_bd": sorted(set(bd_por_ref) - set(por_ref)), "so_api": len(set(por_ref) - set(bd_por_ref)),
         "col": defaultdict(Counter), "motivos": defaultdict(Counter)}
    pares = [(por_ref[k], bd_por_ref[k]) for k in bd_por_ref if k in por_ref]
    campos = (("interested", "visita_interessado"), ("positivePoints", "visita_pontos_positivos"),
              ("negativePoints", "visita_pontos_negativos"), ("aboutBusiness", "visita_sobre_negocio"))
    r["tabelas"] = {ca: aprender([(_ids(v, ca), b.get(col)) for v, b in pares]) for ca, col in campos}
    c = r["col"]
    for v, b in pares:
        c["oportunidade_ref"][nome_de_lead.get(v.get("leadId")) == b["oportunidade_ref"]] += 1
        c["visita_imovel_ref"][ref_de_imovel.get(v.get("realestateId")) == b.get("visita_imovel_ref")] += 1
        c["visita_data"][(v.get("date") or "")[:10] == (b.get("visita_data") or "")[:10]] += 1
        c["visita_anulada"][("Sim" if v.get("cancelled") else "Não") == b.get("visita_anulada")] += 1
        c["visita_cliente"][_n(v.get("potencialClientName")) == _n(b.get("visita_cliente"))] += 1
        c["visita_imovel_proprietario"][_n(v.get("ownerName")) == _n(b.get("visita_imovel_proprietario"))] += 1
        c["visita_observacoes"][ok := _n(v.get("observations")) == _n(b.get("visita_observacoes"))] += 1
        if not ok:
            r["motivos"]["visita_observacoes"]["BD vazia" if not _n(b.get("visita_observacoes")) else "API vazia" if not _n(v.get("observations")) else
                                               "BD é prefixo/contém" if _n(b["visita_observacoes"]) in _n(v["observations"]) or _n(v["observations"]) in _n(b["visita_observacoes"]) else "texto diferente"] += 1
        c["responsavel(securityUserId)"][ok := _n(utilizadores.get(v.get("securityUserId"))) == _n(b.get("visita_responsavel"))] += 1
        if not ok:
            r["motivos"]["responsavel"]["utilizador fora do mapa" if v.get("securityUserId") not in utilizadores else "BD sem responsável" if not b.get("visita_responsavel") else "nome diferente"] += 1
        c["responsavel(ownerId)"][_n(utilizadores.get(v.get("ownerId"))) == _n(b.get("visita_responsavel"))] += 1
        c["responsavel(visita, senão oportunidade)"][(_n(utilizadores.get(v.get("securityUserId"))) or _n((resp_da_oportunidade or {}).get(b["oportunidade_ref"])))
                                                      == _n(b.get("visita_responsavel"))] += 1
        for ca, col in campos:
            tab = r["tabelas"][ca][0]
            api_nomes = {_n(tab[i]) for i in _ids(v, ca) if i in tab}
            c[col][ok := api_nomes == {_n(x) for x in _nomes(b.get(col))}] += 1
            if not ok:
                r["motivos"][col]["BD vazia" if not _nomes(b.get(col)) else "API vazia" if not api_nomes else "nomes diferentes"] += 1
    return r


def _com_espera(f):
    for _ in range(8):
        try:
            return f()
        except Exception as e:
            if "429" not in str(e):
                raise
            time.sleep(60)
    raise RuntimeError("429 persistente")


def main() -> None:
    from app.db.supabase_client import get_supabase
    from app.integrations import ego_api, visitas_api

    ativas = ego_api.oportunidades_ativas()
    nome_de_lead = {o["id"]: o["name"] for o in ativas if o.get("name")}
    refs = set(nome_de_lead.values())
    api = [v for v in _com_espera(lambda: visitas_api.da_api(list(nome_de_lead))) if v.get("leadId") in nome_de_lead]
    sb, bd, ini = get_supabase(), [], 0
    while True:
        lote = sb.table("visitas").select("*").order("visita_ref_ego").range(ini, ini + 999).execute().data
        bd += [x for x in lote if x["oportunidade_ref"] in refs]
        ini += 1000
        if len(lote) < 1000:
            break
    ref_de_imovel = {i["id"]: (i.get("reference") or "").strip() for i in _com_espera(ego_api.todos_os_imoveis) if i.get("id")}
    r = comparar(api, bd, nome_de_lead, ref_de_imovel, ego_api.utilizadores())
    print(f"visitas: API {r['api']}, BD (oportunidades ativas) {r['bd']}; só na BD {len(r['so_bd'])}, só na API {r['so_api']}")
    for col, c in sorted(r["col"].items()):
        t = c[True] + c[False]
        print(f"  {col:34} {100 * c[True] / t:5.1f} % ({c[True]}/{t})" if t else f"  {col}: n/a")
    for col, m in sorted(r["motivos"].items()):
        print("  divergências", col, dict(m))
    for campo, (tab, bal) in r["tabelas"].items():
        print(campo, dict(bal), dict(sorted(tab.items())))


def demo() -> None:
    api = [{"visitReference": "VF_1", "leadId": 1, "realestateId": 10, "date": "2026-11-13T00:00:00", "cancelled": False, "interested": 7,
            "positivePoints": [5], "negativePoints": [], "aboutBusiness": [], "potencialClientName": "Pessoa Teste", "ownerName": "Dono Teste",
            "observations": "ok", "securityUserId": 3, "ownerId": 4},
           {"visitReference": "VF_2", "leadId": 1, "realestateId": 10, "date": "2026-11-14T00:00:00", "cancelled": True, "interested": 7,
            "positivePoints": [5, 6], "negativePoints": [], "aboutBusiness": [], "potencialClientName": "Pessoa Teste", "ownerName": "Dono Teste",
            "observations": "", "securityUserId": 3, "ownerId": 4}]
    base = {"oportunidade_ref": "VEN_1", "visita_imovel_ref": "FH0001", "visita_anulada": "Não", "visita_interessado": "Interessado",
            "visita_pontos_negativos": None, "visita_sobre_negocio": None, "visita_cliente": "Pessoa Teste",
            "visita_imovel_proprietario": "Dono Teste", "visita_responsavel": "Consultora Teste"}
    bd = [{**base, "visita_ref_ego": "VF_1", "visita_data": "2026-11-13", "visita_pontos_positivos": "Boa localização", "visita_observacoes": "ok"},
          {**base, "visita_ref_ego": "VF_2", "visita_data": "2026-11-14", "visita_anulada": "Sim", "visita_observacoes": None,
           "visita_pontos_positivos": "Boa localização, Potencial de negócio"},
          {"visita_ref_ego": "VF_9", "oportunidade_ref": "VEN_1"}]
    r = comparar(api, bd, {1: "VEN_1"}, {10: "FH0001"}, {3: "Consultora Teste", 4: "Dono Teste"})
    assert r["api"] == 2 and r["so_bd"] == ["VF_9"] and r["so_api"] == 0
    assert r["tabelas"]["positivePoints"][0] == {5: "Boa localização", 6: "Potencial de negócio"}, "aprende o 5 pelo caso de 1 e o 6 por exclusão"
    assert r["tabelas"]["interested"][0] == {7: "Interessado"}
    for col, c in r["col"].items():
        if col not in ("responsavel(ownerId)", "responsavel(securityUserId)"):
            assert c[False] == 0, f"{col} devia bater: {dict(c)}"
    assert r["col"]["responsavel(ownerId)"][True] == 0, "ownerId é o dono do imóvel, não a consultora"
    print("comparar visitas OK")


if __name__ == "__main__":
    demo() if "--teste" in sys.argv else main()
