"""Notas da API do eGO vs notas gravadas pelo relatório do scraper (P1 de `docs/fases/api-a-substituir-scraper-acelerado-plano.md`).
SÓ LEITURA, sem PII: nunca imprime texto, nome nem telefone, só contagens, códigos e o código Unicode do 1.º carácter.

    python scripts/comparar_notas_api_relatorio.py              # últimos 14 dias
    python scripts/comparar_notas_api_relatorio.py --desde 2026-11-15
    python scripts/comparar_notas_api_relatorio.py --teste      # auto-teste sem rede

Critério para parar de gravar notas pelo relatório (`RELATORIO_SEM_NOTAS`): autor e tipo ≥ 99 % durante 3 dias úteis seguidos, e **nenhuma nota
do relatório em falta na API** (coluna `so_relat.`), com as divergências explicadas.
"""

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations import ego_notas  # noqa: E402


_SUFIXO_PORTAL = "registado no portal figueira home por"  # = scraper/upsert.py


def _k(ref: str, dia: str, texto: str) -> tuple[str, str, str]:
    """Chave de emparelhamento: como `ego_notas.chave`, mas sem os símbolos à cabeça (a API traz um ícone que o relatório não traz)."""
    t = re.sub(r"\s+", " ", ego_notas.texto_de(texto)).strip().lower()
    if (i := t.find(_SUFIXO_PORTAL)) >= 0:  # o relatório leva o sufixo do portal e a API não: uma nota curta nunca bateria
        t = t[:i].rstrip(" —–-")
    return ref, dia, re.sub(r"^[^\w]+", "", t)[:50]


def _kfim(ref: str, dia: str, texto: str) -> tuple[str, str, str]:
    """2.ª chave, pelos 40 últimos caracteres: apanha a nota a que a API acrescentou algo no início (um rótulo ou ícone no meio das primeiras palavras)."""
    t = re.sub(r"\s+", " ", ego_notas.texto_de(texto)).strip().lower()
    if (i := t.find(_SUFIXO_PORTAL)) >= 0:
        t = t[:i].rstrip(" —–-")
    return ref, dia, t[-40:]


def _vazio(v) -> bool:
    return v is None or str(v).strip() == ""


def comparar(api: list[dict], relatorio: list[dict], utilizadores: dict[int, str], tipos: dict[int, str]) -> dict:
    """`api`: notas da API (`id`, `objectRef`, `dia`, `description`, `securityUserId`, `historicTypeId`).
    `relatorio`: linhas de `notas` sem `nota_ego_id` (`oportunidade_ref`, `nota_data_iso`, `nota_texto`, `nota_autor`, `nota_tipo`)."""
    por_chave: dict[tuple, list[dict]] = defaultdict(list)
    for n in api:
        por_chave[_k(n["objectRef"], n["dia"], n["description"])].append(n)
    por_fim: dict[tuple, list[dict]] = defaultdict(list)
    for n in api:
        por_fim[_kfim(n["objectRef"], n["dia"], n["description"])].append(n)
    dias_api = {(n["objectRef"], n["dia"]) for n in api}
    r = {"pares": 0, "dias": defaultdict(Counter), "autor": Counter(), "tipo": Counter(), "autor_dif": Counter(), "tipo_dif": Counter(),
         "so_relatorio": Counter(), "icone_api": Counter(), "emparelhadas_pelo_fim": 0}
    usadas: set[int] = set()
    for x in relatorio:
        dia = x["nota_data_iso"] or ""
        d = r["dias"][dia]
        d["relatorio"] += 1
        cands = [n for n in por_chave.get(_k(x["oportunidade_ref"], dia, x["nota_texto"]), []) if n["id"] not in usadas]
        if not cands:  # 2.ª tentativa, pelo fim do texto
            cands = [n for n in por_fim.get(_kfim(x["oportunidade_ref"], dia, x["nota_texto"]), []) if n["id"] not in usadas and len(x["nota_texto"] or "") > 40]
            if cands:
                r["emparelhadas_pelo_fim"] += 1
        if not cands:
            d["so_relatorio"] += 1
            r["so_relatorio"]["API tem outra nota nesse dia" if (x["oportunidade_ref"], dia) in dias_api else "API sem notas nesse dia"] += 1
            continue
        n = cands[0]
        usadas.add(n["id"])
        r["pares"] += 1
        d["pares"] += 1
        nome_api = utilizadores.get(n.get("securityUserId"))
        if _vazio(nome_api):
            r["autor"]["api sem nome (utilizador fora do eGO)"] += 1
        elif _vazio(x.get("nota_autor")):
            r["autor"]["relatorio sem autor"] += 1
        elif nome_api.strip().lower() == x["nota_autor"].strip().lower():
            r["autor"]["igual"] += 1
            d["autor_igual"] += 1
        else:
            r["autor"]["diferente"] += 1
            r["autor_dif"][(n.get("securityUserId"), "mesmo 1.º nome" if nome_api.split()[0].lower() == x["nota_autor"].split()[0].lower() else "outro nome")] += 1
        tipo_api = tipos.get(n.get("historicTypeId")) or ego_notas._TIPOS.get(n.get("historicTypeId"))
        if _vazio(tipo_api) and _vazio(x.get("nota_tipo")):
            r["tipo"]["ambos vazios"] += 1
        elif _vazio(x.get("nota_tipo")):
            r["tipo"]["so a API tem tipo"] += 1
        elif _vazio(tipo_api):
            r["tipo"]["so o relatorio tem tipo"] += 1
            r["tipo_dif"][(n.get("historicTypeId"), "relatorio tem tipo, API codigo sem nome")] += 1
        elif tipo_api.strip().lower() == x["nota_tipo"].strip().lower():
            r["tipo"]["igual"] += 1
            d["tipo_igual"] += 1
        else:
            r["tipo"]["diferente"] += 1
            r["tipo_dif"][(n.get("historicTypeId"), "nome diferente")] += 1
    for n in api:  # notas só da API: o 1.º carácter diz se o ícone explica a diferença
        if n["id"] not in usadas:
            c = ego_notas.texto_de(n["description"])[:1]
            r["icone_api"]["começa por símbolo U+%04X" % ord(c) if c and not re.match(r"\w", c) else "começa por letra/dígito"] += 1
    return r


def taxa(c: Counter, *erros: str) -> str:
    ok, mal = c["igual"], sum(c[e] for e in erros)
    return f"{100 * ok / (ok + mal):.1f} % ({ok}/{ok + mal})" if ok + mal else "n/a"


def _imprimir(r: dict) -> None:
    print(f"pares emparelhados: {r['pares']} (dos quais {r['emparelhadas_pelo_fim']} só pelo fim do texto)")
    print("autor:", dict(r["autor"]), "-> concordância", taxa(r["autor"], "diferente"))
    print("tipo :", dict(r["tipo"]), "-> concordância", taxa(r["tipo"], "diferente", "so o relatorio tem tipo"))
    print("autor diferente (id do utilizador, relação dos nomes):", dict(r["autor_dif"]))
    print("tipo diferente (código da API, motivo):", dict(r["tipo_dif"]))
    print("notas SÓ NO RELATÓRIO (têm de ser 0 para desligar):", dict(r["so_relatorio"]))
    print("notas só na API e o seu 1.º carácter (nenhum emparelhamento):", dict(r["icone_api"]))
    print("\ndia         relat.  pares  so_relat.  autor_igual  tipo_igual")
    for dia in sorted(r["dias"]):
        d = r["dias"][dia]
        print(f"{dia}  {d['relatorio']:6}  {d['pares']:5}  {d['so_relatorio']:9}  {d['autor_igual']:11}  {d['tipo_igual']:10}")


def _relatorio_da_bd(refs: set[str], desde: str) -> list[dict]:
    from app.db.supabase_client import get_supabase

    sb, saida, ini = get_supabase(), [], 0
    while True:
        q = (sb.table("notas").select("oportunidade_ref,nota_data_iso,nota_texto,nota_autor,nota_tipo,nota_ego_id")
             .gte("nota_data_iso", desde).order("id").range(ini, ini + 999))
        lote = q.execute().data
        saida += [x for x in lote if x["nota_ego_id"] is None and x["oportunidade_ref"] in refs]
        ini += 1000
        if len(lote) < 1000:
            return saida


def main() -> None:
    from app.integrations import ego_api

    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default=(date.today() - timedelta(days=14)).isoformat())
    a = ap.parse_args()
    ativas = ego_api.oportunidades_ativas()
    nome_de = {o["id"]: o["name"] for o in ativas if o.get("name")}
    for _ in range(8):  # o eGO responde 429 a leituras seguidas: espera e repete
        try:
            todas = ego_notas.notas_da_api(list(nome_de))
            break
        except Exception as e:
            if "429" not in str(e):
                raise
            time.sleep(60)
    api = [{**n, "objectRef": nome_de[n["objectId"]], "dia": (n.get("createDate") or "")[:10]}
           for n in todas if n.get("objectId") in nome_de and (n.get("createDate") or "")[:10] >= a.desde]
    relatorio = _relatorio_da_bd(set(nome_de.values()), a.desde)
    print(f"desde {a.desde}: {len(api)} notas na API, {len(relatorio)} do relatório (oportunidades ativas)")
    _imprimir(comparar(api, relatorio, ego_api.utilizadores(), ego_api.tipos_de_nota()))


def demo() -> None:
    """Auto-teste: emparelha apesar do ícone, conta autor/tipo certos e acusa a nota que só o relatório tem."""
    def n(i, ref, txt, user=1, tipo=0, dia="2026-11-20"):
        return {"id": i, "objectRef": ref, "dia": dia, "description": txt, "securityUserId": user, "historicTypeId": tipo}

    def x(ref, txt, autor, tipo=None, dia="2026-11-20"):
        return {"oportunidade_ref": ref, "nota_data_iso": dia, "nota_texto": txt, "nota_autor": autor, "nota_tipo": tipo}

    api = [n(1, "A", "Ligou ao cliente"), n(2, "A", "☎ Marcou visita", user=2), n(3, "B", "<p>Ponto de situação</p>", user=1, tipo=81),
           n(4, "C", "Outra", user=3), n(5, "D", "só na API")]
    rel = [x("A", "Ligou ao cliente", "Ana Teste"), x("A", "Marcou visita", "Rui Teste"), x("B", "Ponto de situação", "Ana Teste", "Ponto de Situação"),
           x("C", "Outra", "Ana Teste"), x("E", "so no relatorio", "Ana Teste")]
    r = comparar(api, rel, {1: "Ana Teste", 2: "Rui Teste"}, {81: "Ponto de Situação"})
    assert r["pares"] == 4 and r["autor"]["igual"] == 3 and r["autor"]["api sem nome (utilizador fora do eGO)"] == 1
    assert r["tipo"]["igual"] == 1 and r["tipo"]["ambos vazios"] == 3
    assert r["so_relatorio"] == Counter({"API sem notas nesse dia": 1}) and r["icone_api"] == Counter({"começa por letra/dígito": 1})
    assert taxa(r["autor"], "diferente") == "100.0 % (3/3)"
    r = comparar([n(1, "A", "Visita")], [x("A", "Visita — registado no portal Figueira Home por Ana Teste", "Ana Teste")], {1: "Ana Teste"}, {})
    assert r["pares"] == 1, "o sufixo do portal não impede o emparelhamento de uma nota curta"
    r = comparar([n(1, "A", "texto")], [x("A", "texto", "Outra Pessoa")], {1: "Ana Teste"}, {})
    assert r["autor"]["diferente"] == 1 and r["autor_dif"] == Counter({(1, "outro nome"): 1})
    r = comparar([n(1, "A", "Contacto: ligou ao cliente e combinou visita para sexta-feira")], [x("A", "ligou ao cliente e combinou visita para sexta-feira", "Ana Teste")], {1: "Ana Teste"}, {})
    assert r["pares"] == 1 and r["emparelhadas_pelo_fim"] == 1, "a API acrescentou um rótulo ao início: emparelha pelo fim"
    print("comparar OK")


if __name__ == "__main__":
    demo() if "--teste" in sys.argv else main()
