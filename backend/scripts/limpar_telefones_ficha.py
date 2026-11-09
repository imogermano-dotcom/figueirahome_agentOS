"""F3 do pedido #58: fichas de `contactos` com `telefone` fora da regra (>15 dígitos ou lista `, ; /`).

    cd backend && python scripts/limpar_telefones_ficha.py                       # corrida em seco: só conta e classifica
    cd backend && python scripts/limpar_telefones_ficha.py --aplicar COPIA.json  # escreve (backup dos valores antigos em COPIA.json)

Não imprime nomes nem telefones, só contagens e o início do `id` dos casos por rever à mão.
Regra da 0058: `telefone` = um só número, no máximo 15 dígitos. Classes:
  repetido      o mesmo número duas vezes (colado ou em lista)            → telefone := um só bloco
  dois_numeros  dois números diferentes (9+9 colados, ou lista)           → telefone := o primeiro; o segundo vai
                                                                            para `telemovel` se estiver vazio
  rever         qualquer outra coisa (não se adivinha)                    → à mão
"""
import json
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app.db.supabase_client import get_supabase  # noqa: E402


def classificar(telefone: str) -> tuple[str, list[str]]:
    """(classe, números). Os números só têm dígitos, sem `00`; PT = 9 dígitos, E.164 até 15."""
    partes = [re.sub(r"\D", "", p) for p in re.split(r"[,;/]", telefone)]
    partes = [p[2:] if p.startswith("00") else p for p in partes if p]
    if len(partes) == 1:
        d = partes[0]
        n = len(d)
        if n % 2 == 0 and d[: n // 2] == d[n // 2:] and (n // 2 == 9 or 10 <= n // 2 <= 15):
            partes = [d[: n // 2], d[n // 2:]]
        elif n == 18 and d[0] in "923" and d[9] in "923":
            partes = [d[:9], d[9:]]
        else:
            return "rever", partes
    if any(len(p) < 9 or len(p) > 15 for p in partes):
        return "rever", partes
    unicos = list(dict.fromkeys(partes))
    return ("repetido" if len(unicos) == 1 else "dois_numeros"), unicos


def main() -> None:
    sb = get_supabase()
    linhas, i = [], 0
    while True:
        lote = (sb.table("contactos").select("id,telefone,telemovel,ego_link,meta_lead_id,agente")
                .not_.is_("telefone", "null").order("id").range(i, i + 999).execute().data)
        linhas += lote
        if len(lote) < 1000:
            break
        i += 1000

    fora = [l for l in linhas
            if len(re.sub(r"\D", "", l["telefone"] or "")) > 15 or re.search(r"[,;/]", l["telefone"] or "")]
    print(f"contactos com telefone: {len(linhas)} | fora da regra: {len(fora)} (esperado 168)")

    por_classe, origem, mover = Counter(), Counter(), Counter()
    rever, a_escrever = [], []
    for l in fora:
        classe, nums = classificar(l["telefone"])
        por_classe[classe] += 1
        origem[(classe, "com ego_link" if l["ego_link"] else "sem ego_link")] += 1
        if classe == "repetido":
            a_escrever.append((l, {"telefone": nums[0]}))
        if classe == "dois_numeros":
            vazio = not (l["telemovel"] or "").strip()
            if vazio:  # com `telemovel` ocupado o segundo número fica por rever à mão
                a_escrever.append((l, {"telefone": nums[0], "telemovel": nums[1]}))
            mover["segundo vai para telemovel (vazio)" if vazio else "telemovel já ocupado (segundo fica por registar)"] += 1
        if classe == "rever":
            rever.append(l)

    print("\npor classe:", dict(por_classe))
    print("origem:")
    for (c, o), n in sorted(origem.items()):
        print(f"  {c:13} {o:13} {n}")
    print("dois_numeros:", dict(mover))
    print(f"\nrever à mão: {len(rever)}")
    for l in rever:
        n = len(re.sub(r"\D", "", l["telefone"]))
        sep = "lista" if re.search(r"[,;/]", l["telefone"]) else "colado"
        print(f"  {l['id'][:8]}  {n:2} dígitos  {sep}  {'ego_link' if l['ego_link'] else 'sem ego_link'}")
    print(f"\na escrever: {len(a_escrever)} (repetidos + dois números com telemovel vazio)")
    if "--aplicar" not in sys.argv:
        print("(dry) nada escrito.")
        return
    copia = sys.argv[sys.argv.index("--aplicar") + 1]
    with open(copia, "w", encoding="utf-8") as f:  # fora do repo: tem telefones
        json.dump([{"id": l["id"], "telefone": l["telefone"], "telemovel": l["telemovel"]} for l, _ in a_escrever], f)
    feitas = 0
    for l, novo in a_escrever:
        r = sb.table("contactos").update(novo).eq("id", l["id"]).eq("telefone", l["telefone"]).execute()
        feitas += len(r.data)
    print(f"escritas: {feitas} de {len(a_escrever)} (backup em {copia})")


if __name__ == "__main__":
    main()
