"""Fecha as tarefas pendentes legadas (`Ativas`/`Arquivadas`, sem `ego_id`) que a API do eGO já não tem pendentes (pedido #8).

    cd backend && python scripts/fechar_tarefas_legadas.py            # só conta (A/B/C), não escreve
    cd backend && python scripts/fechar_tarefas_legadas.py --aplicar  # fecha A e B, guarda os ids em --ids
    cd backend && python scripts/fechar_tarefas_legadas.py --aplicar --incluir-c  # fecha também o C

A = a oportunidade não tem nenhuma pendente na API · B = a mesma chave (ref, título, data) existe viva · C = o resto (só com --incluir-c).
Sem nomes nem telefones na saída. Plano: docs/fases/tarefas-legadas-plano.md
"""
import argparse
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

CHAVE = ["oportunidade_ref", "tarefa_titulo", "tarefa_due_raw"]


def classificar(legadas: list[dict], vivas: list[dict]) -> dict:
    """`vivas` = pendentes da API já no formato da BD. Devolve ids por camada; C inclui `c_mesmo_titulo` (só informativo)."""
    refs_vivas = {v["oportunidade_ref"] for v in vivas}
    chaves_vivas = {tuple(v.get(c) for c in CHAVE) for v in vivas}
    titulos_vivos = {(v["oportunidade_ref"], v.get("tarefa_titulo")) for v in vivas}
    a, b, c = [], [], []
    for t in legadas:
        if t.get("ego_id") is not None or t.get("origem_lista") == "todas_as_colunas":
            continue
        if t["oportunidade_ref"] not in refs_vivas:
            a.append(t)
        elif tuple(t.get(k) for k in CHAVE) in chaves_vivas:
            b.append(t)
        else:
            c.append(t)
    return {"A": a, "B": b, "C": c,
            "c_mesmo_titulo": sum(1 for t in c if (t["oportunidade_ref"], t.get("tarefa_titulo")) in titulos_vivos)}


def a_fechar(r: dict, incluir_c: bool) -> list[dict]:
    return r["A"] + r["B"] + (r["C"] if incluir_c else [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--incluir-c", action="store_true", help="fecha também o C (decisão de 24/11)")
    ap.add_argument("--ids", default="tarefas_legadas_fechadas.json", help="onde guardar os ids fechados (fora do repo)")
    args = ap.parse_args()

    from app.db.supabase_client import get_supabase
    from app.integrations import tarefas_api

    sb = get_supabase()
    snap = tarefas_api.snapshot()  # levanta se a API vier incompleta: nunca se fecha com dados parciais
    vivas = snap["tarefas"]
    legadas = tarefas_api._paginar(lambda a, b: sb.table("tarefas")
        .select("id,oportunidade_ref,tarefa_titulo,tarefa_due_raw,origem_lista,ego_id,criado_em,tipo_oportunidade")
        .eq("tarefa_status", "pendente").neq("origem_lista", tarefas_api.ORIGEM).order("id").range(a, b).execute().data)
    r = classificar(legadas, vivas)
    print(f"API: {snap['brutas']} pendentes ({len(vivas)} com oportunidade) | legadas pendentes: {len(legadas)}")
    print(f"A (oportunidade sem pendentes na API): {len(r['A'])} | B (mesma chave viva): {len(r['B'])} | C (resto): {len(r['C'])}"
          f" (dos quais {r['c_mesmo_titulo']} com o mesmo título vivo na oportunidade)")
    print("C por origem:", dict(Counter(t["origem_lista"] for t in r["C"])))
    print("C por mês de entrada na BD:", dict(sorted(Counter((t["criado_em"] or "?")[:7] for t in r["C"]).items())))
    print("C por tipo:", dict(Counter(t["tipo_oportunidade"] for t in r["C"])))
    print("A por origem:", dict(Counter(t["origem_lista"] for t in r["A"])))

    fechar = a_fechar(r, args.incluir_c)
    if not args.aplicar:
        print(f"(dry) nada escrito; --aplicar fecharia {len(fechar)}" + ("" if args.incluir_c else " (A+B; --incluir-c junta o C)"))
        return
    with open(args.ids, "w", encoding="utf-8") as f:
        json.dump([t["id"] for t in fechar], f)  # antes de escrever: é a reversão
    for i in range(0, len(fechar), 200):
        sb.table("tarefas").update({"tarefa_status": tarefas_api.ESTADO_FECHADA}).in_("id", [t["id"] for t in fechar[i:i + 200]]).execute()
    print(f"fechadas {len(fechar)}; ids em {args.ids}")


if __name__ == "__main__":
    main()
