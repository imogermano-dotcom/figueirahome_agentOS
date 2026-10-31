"""Notas das oportunidades ativas pela API do eGO vs `notas` no Supabase (fase A2). Dry-run por omissão: SÓ LEITURA, sem PII.

    python scripts/ego_api_notas.py                # resumo das notas só na API, com texto
    python scripts/ego_api_notas.py --desde 2026-10-01   # só notas escritas a partir desta data

Chave de comparação: (oportunidade_ref, dia da nota, 50 primeiros caracteres do texto sem HTML), a mesma de `docs/fases/ego-api-notas-plano.md`.
"""

import argparse
import html
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def texto_de(description: str | None) -> str:
    """HTML da nota → texto simples (quebras de linha mantidas)."""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", description or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def chave(ref: str, dia: str, texto: str) -> tuple[str, str, str]:
    return ref, dia, re.sub(r"\s+", " ", texto).strip().lower()[:50]


def so_na_api(api: list[dict], nome_de: dict[int, str], na_bd: set[tuple]) -> list[dict]:
    """Notas da API com texto que a BD não tem (por chave). Uma só por chave: repetidas na API contam uma vez."""
    vistas, saida = set(na_bd), []
    for n in api:
        ref, texto = nome_de.get(n["objectId"]), texto_de(n.get("description"))
        if not ref or not texto:
            continue
        k = chave(ref, (n.get("createDate") or "")[:10], texto)
        if k not in vistas:
            vistas.add(k)
            saida.append({"ego_id": n["id"], "ref": ref, "dia": k[1], "texto": texto})
    return saida


def linha_de_nota(n: dict) -> dict:
    """Linha para `notas`. O que a API não dá (url, cliente_nome, autor) fica de fora; `contacto_id` herda-se por RPC."""
    d = n["dia"]
    return {
        "oportunidade_ref": n["ref"], "nota_texto": n["texto"][:1200], "nota_ego_id": n["ego_id"],
        "nota_data_raw": f"{d[8:10]}/{d[5:7]}/{d[:4]}", "nota_data_iso": d,
        "nota_origem": "crm", "origem_lista": "todas_as_colunas",
    }


def _notas_da_api(ids: list[int]) -> list[dict]:
    import httpx
    from app.config import settings
    from app.integrations import ego_api
    saida: list[dict] = []
    with httpx.Client(timeout=120, headers={"User-Agent": ego_api._UA}) as c:
        s = ego_api._sessao_valida(c)
        for i in range(0, len(ids), 200):
            pag = 0
            while True:
                r = c.post(f"{settings.egoapi_base_url}/note/Note/ListNotesByPage", params={"applicationId": s["application_id"]},
                           json={"objectName": 3, "objectIds": ids[i:i + 200], "pageIndex": pag, "numberOfRecords": 1000,
                                 "applicationId": s["application_id"]},
                           headers={"Authorization": f"Bearer {s['token']}"})
                r.raise_for_status()
                it = r.json()["items"]
                saida += it
                if len(it) < 1000:
                    break
                pag += 1
    return saida


def _chaves_da_bd(refs: set[str]) -> set[tuple]:
    from app.db.supabase_client import get_supabase
    sb, ini, ks = get_supabase(), 0, set()
    while True:
        l = sb.table("notas").select("oportunidade_ref,nota_data_iso,nota_texto").order("id").range(ini, ini + 999).execute().data
        ks |= {chave(x["oportunidade_ref"], x["nota_data_iso"] or "", texto_de(x["nota_texto"])) for x in l if x["oportunidade_ref"] in refs}
        ini += 1000
        if len(l) < 1000:
            return ks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="")
    a = ap.parse_args()
    from app.integrations import ego_api
    ativas = ego_api.oportunidades_ativas()
    nome_de = {o["id"]: o["name"] for o in ativas if o.get("name")}
    novas = [n for n in so_na_api(_notas_da_api(list(nome_de)), nome_de, _chaves_da_bd(set(nome_de.values()))) if n["dia"] >= a.desde]
    por_ref = Counter(n["ref"] for n in novas)
    print(f"notas por gravar: {len(novas)} em {len(por_ref)} oportunidades (desde {a.desde or 'sempre'})")
    print("por mês da nota:", sorted(Counter(n["dia"][:7] for n in novas).items()))
    print("notas por oportunidade (nº de oportunidades):", sorted(Counter(por_ref.values()).items()))
    print("texto: máx", max((len(n["texto"]) for n in novas), default=0), "caracteres;", sum(len(n["texto"]) > 1200 for n in novas), "cortadas a 1200")
    for mes in sorted({n["dia"][:7] for n in novas}):
        print(f"  {mes}: {len({n['ref'] for n in novas if n['dia'][:7] == mes})} oportunidades")


if __name__ == "__main__":
    main()
