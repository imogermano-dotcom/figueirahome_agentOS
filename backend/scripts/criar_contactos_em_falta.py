"""Pedido #4, etapa 3: pessoas do eGO que as oportunidades referem e que não estão em `contactos`.
Plano: docs/fases/contactos-em-falta-do-ego-plano.md

    cd backend && python scripts/criar_contactos_em_falta.py --cache <ficheiro fora do repo>   # dry-run: só lê, nunca escreve
    ... --gravar --limite 20 --ids <ficheiro fora do repo>   # completa e cria (1.º lote pequeno)

Lê o eGO (`GetEntity`, ~1 h por causa do 429) e classifica cada pessoa:
  a = já existe linha com o mesmo `ego_person_id` · b = UMA linha sem `ego_link` com o mesmo telefone/email (completar, não criar)
  c = várias linhas, ou a linha é de outra pessoa do eGO (lista ao Miguel) · d = sem correspondência (criar)
O cache guarda nomes, telefones e emails: fica FORA do repo (público). A saída só tem contagens.
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")


def digitos9(texto: str | None) -> set[str]:
    """Números portugueses (9 dígitos) de um campo, mesmo que tenha vários («912 345 678, 233 111 222»)."""
    achados = set()
    for parte in re.split(r"[,;/|]", texto or ""):
        d = re.sub(r"\D", "", parte)
        if len(d) >= 9:
            achados.add(d[-9:])
    return achados


def pessoa_do_ego(e: dict) -> dict:
    """O que interessa de um `GetEntity`. Telefone ou email decide-se pelo conteúdo («@»), não pelo tipo (por confirmar)."""
    telefones, emails, tipos = set(), set(), []
    for c in e.get("personalContacts") or []:
        valor = str(c.get("contact") or "").strip()
        tipos.append((c.get("personalContactTypeId"), "@" in valor))
        if "@" in valor:
            emails.add(valor.lower())
        else:
            telefones |= digitos9(valor)
    return {
        "nome": " ".join(p for p in (e.get("firstName"), e.get("lastName")) if p and str(p).strip()).strip(),
        "telefones": sorted(telefones), "emails": sorted(emails), "tipos": tipos,
        "empresa": bool(e.get("isCompany")), "alter": (e.get("alterDate") or "")[:10],
    }


def indices(linhas: list[dict]) -> tuple[dict, dict, dict]:
    """`contactos` por telefone (9 dígitos), por email e por `ego_person_id`."""
    por_tel, por_email, por_pessoa = collections.defaultdict(set), collections.defaultdict(set), {}
    for c in linhas:
        for campo in ("telefone", "telemovel"):
            for t in digitos9(c.get(campo)):
                por_tel[t].add(c["id"])
        if c.get("email"):
            por_email[c["email"].strip().lower()].add(c["id"])
        if c.get("ego_person_id"):
            por_pessoa[c["ego_person_id"]] = c["id"]
    return por_tel, por_email, por_pessoa


def classificar(pid: int, p: dict, linhas_por_id: dict, por_tel: dict, por_email: dict, por_pessoa: dict) -> tuple[str, list[str]]:
    if pid in por_pessoa:
        return "a", [por_pessoa[pid]]
    candidatas = set()
    for t in p["telefones"]:
        candidatas |= por_tel.get(t, set())
    for m in p["emails"]:
        candidatas |= por_email.get(m, set())
    if not candidatas:
        return "d", []
    if len(candidatas) == 1:
        (cid,) = candidatas
        c = linhas_por_id[cid]
        if not c.get("ego_link") and not c.get("ego_person_id"):
            return "b", [cid]
    return "c", sorted(candidatas)


def _todos(sb, tabela: str, cols: str) -> list[dict]:
    out, i = [], 0
    while True:
        lote = sb.table(tabela).select(cols).order("id").range(i, i + 999).execute().data
        out += lote
        i += 1000
        if len(lote) < 1000:
            return out


def em_falta(sb, ativas: list[dict], arquivadas: list[dict], pessoas_bd: set[int]) -> dict[int, set[str]]:
    """Pessoa do eGO → referências das oportunidades sem `contacto_id` que a referem e que não está em `contactos`."""
    ops, i = {}, 0
    while True:
        lote = sb.table("oportunidades").select("ego_lead_id,contacto_id").not_.is_("ego_lead_id", "null").order("ego_lead_id").range(i, i + 999).execute().data
        for x in lote:
            ops[x["ego_lead_id"]] = x["contacto_id"]
        i += 1000
        if len(lote) < 1000:
            break
    falta: dict[int, set[str]] = {}
    for o in ativas + arquivadas:
        if o["id"] not in ops or ops[o["id"]]:
            continue
        a, c = o.get("potencialClientId"), o.get("ownerId")
        pid = (c or a) if (o.get("name") or "").startswith("CAP") else (a or c)
        if pid and pid not in pessoas_bd:
            falta.setdefault(pid, set()).add(o["name"])
    return falta


LIGACAO = {"de", "da", "do", "dos", "das", "e", "a", "o"}


def tokens(nome: str | None) -> list[str]:
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    return [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in LIGACAO]


def mesmo_nome(a: str | None, b: str | None) -> bool:
    """Nomes iguais, ou um contido no outro (nome do meio a mais ou a menos). Nunca com um dos lados vazio."""
    A, B = set(tokens(a)), set(tokens(b))
    return bool(A and B and (A <= B or B <= A))


def montar_plano(falta: set[int], cache: dict, por_id: dict, por_tel: dict, por_email: dict, por_pessoa: dict) -> dict:
    """Quem se completa, quem se cria e quem fica para o Miguel. Só campos vazios; nunca cria sem telefone nem email."""
    plano = {"completar": [], "criar": [], "miguel": collections.Counter()}
    for pid in sorted(falta):
        p = cache[str(pid)]
        caso, ids = classificar(pid, p, por_id, por_tel, por_email, por_pessoa)
        if caso == "b" and mesmo_nome(p["nome"], por_id[ids[0]].get("nome")):
            plano["completar"].append((pid, ids[0]))
        elif caso == "d" and (p["telefones"] or p["emails"]) and p["nome"]:
            plano["criar"].append(pid)
        elif caso == "d":
            plano["miguel"]["sem telefone nem email"] += 1
        else:
            plano["miguel"]["b com nome diferente" if caso == "b" else "c (varias linhas ou outra pessoa)"] += 1
    return plano


def campos_a_completar(pid: int, p: dict, linha: dict, prefixo: str) -> dict:
    """Só o que a linha ainda não tem: a identificação do eGO e, se faltarem, telefone e email."""
    novo = {"ego_person_id": pid, "ego_link": f"{prefixo}{pid}"}
    if p["telefones"] and not (linha.get("telefone") or "").strip() and not (linha.get("telemovel") or "").strip():
        novo["telefone"] = novo["telemovel"] = p["telefones"][0]
    if p["emails"] and not (linha.get("email") or "").strip():
        novo["email"] = p["emails"][0]
    return novo


def linha_nova(pid: int, p: dict, prefixo: str) -> dict:
    dia = p["alter"] or datetime.date.today().isoformat()
    linha = {"nome": p["nome"], "ego_link": f"{prefixo}{pid}", "ego_person_id": pid, "origem": "ego_api",
             "criado_em": dia, "ego_atualizado_em": f"{dia}T00:00:00", "whatsapp_permissao": False}
    if p["telefones"]:
        linha["telefone"] = linha["telemovel"] = p["telefones"][0]
    if p["emails"]:
        linha["email"] = p["emails"][0]
    return linha


def gravar(sb, plano: dict, cache: dict, por_id: dict, prefixo: str, ids_path: str, limite: int | None) -> dict:
    """Guarda antes os ids (é a reversão), completa só onde o eGO ainda está vazio e insere linha a linha."""
    completar, criar = plano["completar"][:limite], plano["criar"][:limite]
    json.dump({"completar": [{"pessoa": pid, "contacto": cid} for pid, cid in completar], "criar": criar}, open(ids_path, "w", encoding="utf-8"))
    r = {"completadas": 0, "criadas": 0, "erros": []}
    for pid, cid in completar:
        novo = campos_a_completar(pid, cache[str(pid)], por_id[cid], prefixo)
        try:
            ok = (sb.table("contactos").update(novo).eq("id", cid).is_("ego_link", "null").is_("ego_person_id", "null").execute().data)
            r["completadas"] += 1 if ok else 0
        except Exception as e:  # nunca pára o lote
            r["erros"].append((pid, str(getattr(e, "code", None) or type(e).__name__)))  # nunca o texto: traz o nome
    for pid in criar:
        try:
            sb.table("contactos").insert(linha_nova(pid, cache[str(pid)], prefixo)).execute()
            r["criadas"] += 1
        except Exception as e:
            r["erros"].append((pid, str(getattr(e, "code", None) or type(e).__name__)))  # nunca o texto: traz o nome
    sb.table("agente_sync_log").insert({"tipo": "egorealestate_contactos_em_falta", "origem": "manual",
        "resumo": {"completadas": r["completadas"], "criadas": r["criadas"], "erros": len(r["erros"]), "pessoas_completadas": [p for p, _ in completar], "pessoas_criadas": criar}}).execute()
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, help="JSON com as pessoas lidas do eGO (nomes, telefones, emails: fora do repo)")
    ap.add_argument("--gravar", action="store_true", help="completa e cria (por omissão só conta)")
    ap.add_argument("--limite", type=int, default=None, help="com --gravar: no máximo N a completar e N a criar (1.º lote pequeno)")
    ap.add_argument("--ids", default="contactos_em_falta_ids.json", help="onde guardar os ids tocados (fora do repo): é a reversão")
    args = ap.parse_args()

    from app.db.supabase_client import get_supabase
    from app.integrations import ego_api

    sb = get_supabase()
    linhas = _todos(sb, "contactos", "id,nome,ego_link,ego_person_id,telefone,telemovel,email")
    por_tel, por_email, por_pessoa = indices(linhas)
    por_id = {c["id"]: c for c in linhas}
    prefixo = next(c["ego_link"].split("/person/")[0] + "/person/" for c in linhas if "/person/" in (c.get("ego_link") or ""))
    falta = em_falta(sb, ego_api.oportunidades_ativas(), ego_api.oportunidades_arquivadas(), set(por_pessoa))
    print(f"pessoas em falta: {len(falta)} (oportunidades: {sum(len(v) for v in falta.values())})", flush=True)

    cache = json.load(open(args.cache, encoding="utf-8")) if os.path.exists(args.cache) else {}
    feitas = 0
    for pid in sorted(falta):
        if str(pid) in cache:
            continue
        cache[str(pid)] = pessoa_do_ego(ego_api.entidade(pid))
        feitas += 1
        if feitas % 25 == 0:
            json.dump(cache, open(args.cache, "w", encoding="utf-8"))
            print(f"  lidas {len(cache)}/{len(falta)}", flush=True)
    json.dump(cache, open(args.cache, "w", encoding="utf-8"))

    plano = montar_plano(set(falta), cache, por_id, por_tel, por_email, por_pessoa)
    print(f"a completar (linha existente, nome igual): {len(plano['completar'])} | a criar (com telefone ou email): {len(plano['criar'])}")
    print("para o Miguel:", dict(plano["miguel"]))
    if not args.gravar:
        print("(dry) nada escrito; --gravar [--limite N] completa e cria")
        return
    r = gravar(sb, plano, cache, por_id, prefixo, args.ids, args.limite)
    print(f"completadas {r['completadas']} | criadas {r['criadas']} | erros {len(r['erros'])} (ids em {args.ids})")
    for pid, e in r["erros"][:10]:
        print("  erro", pid, e)


if __name__ == "__main__":
    main()
