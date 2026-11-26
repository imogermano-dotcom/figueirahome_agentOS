"""Notas das oportunidades ativas pela API do eGO → `notas` (fase A2, docs/fases/ego-api-notas-plano.md).

A nota não conta como edição da oportunidade, por isso o sync por relatório (janela de 48 h) deixa-as para trás.
Chave de comparação com o histórico (sem `nota_ego_id`): (referência, dia, 50 primeiros caracteres do texto sem HTML)."""

import html
import logging
import re

import httpx

from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import ego_api

logger = logging.getLogger(__name__)


def texto_de(description: str | None) -> str:
    """HTML da nota → texto simples (quebras de linha mantidas)."""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", description or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def chave(ref: str, dia: str, texto: str) -> tuple[str, str, str]:
    return ref, dia, re.sub(r"\s+", " ", texto).strip().lower()[:50]


def so_na_api(api: list[dict], nome_de: dict[int, str], na_bd: set[tuple], ids_na_bd: set[int] = frozenset(), desde: str = "") -> list[dict]:
    """Notas da API com texto que a BD não tem (por `nota_ego_id` ou por chave). Repetidas na API contam uma vez.
    `desde` (AAAA-MM-DD): ignora notas mais antigas."""
    vistas, saida = set(na_bd), []
    for n in api:
        ref, texto, dia = nome_de.get(n["objectId"]), texto_de(n.get("description")), (n.get("createDate") or "")[:10]
        if not ref or not texto or dia < desde or n["id"] in ids_na_bd:
            continue
        k = chave(ref, dia, texto)
        if k not in vistas:
            vistas.add(k)
            saida.append({"ego_id": n["id"], "ref": ref, "dia": dia, "texto": texto,
                          "user_id": n.get("securityUserId"), "tipo_id": n.get("historicTypeId")})
    return saida


# `historicTypeId` da API → `nota_tipo` do relatório (medido a 26/11 em 2 325 notas das duas vias). 0 = nota normal, sem tipo.
_TIPOS = {58: "Tarefa concluída", 81: "Ponto de Situação", 2: "Sistema", 88: "Criação de oportunidade", 4: "Estado oportunidade",
          65: "Clique em Newsletter"}


def linha_de_nota(n: dict, utilizadores: dict[int, str] | None = None) -> dict:
    """Linha para `notas`. Autor (`securityUserId` → nome) e tipo (`historicTypeId`) só se conhecidos; url e cliente_nome copiam-se da
    oportunidade em `gravar`; `contacto_id` herda-se por RPC."""
    d = n["dia"]
    linha = {
        "oportunidade_ref": n["ref"], "nota_texto": n["texto"][:1200], "nota_ego_id": n["ego_id"],
        "nota_data_raw": f"{d[8:10]}/{d[5:7]}/{d[:4]}", "nota_data_iso": d,
        "nota_origem": "crm", "origem_lista": "todas_as_colunas",
    }
    if nome := (utilizadores or {}).get(n.get("user_id")):
        linha["nota_autor"] = nome
    if tipo := _TIPOS.get(n.get("tipo_id")):
        linha["nota_tipo"] = tipo
    return linha


def notas_da_api(ids: list[int]) -> list[dict]:
    """`ListNotesByPage` das oportunidades (ids da API), em lotes de 200. `applicationId` também no corpo, senão HTTP 400."""
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


def da_bd(refs: set[str], desde: str = "") -> tuple[set[tuple], set[int]]:
    """Chaves por texto e `nota_ego_id`s que a BD já tem para essas oportunidades (só notas de `desde` em diante, se dado)."""
    sb, ks, ids, ini = get_supabase(), set(), set(), 0
    while True:
        q = sb.table("notas").select("oportunidade_ref,nota_data_iso,nota_texto,nota_ego_id")
        if desde:
            q = q.gte("nota_data_iso", desde)
        l = q.order("id").range(ini, ini + 999).execute().data
        for x in l:
            if x["oportunidade_ref"] in refs:
                ks.add(chave(x["oportunidade_ref"], x["nota_data_iso"] or "", texto_de(x["nota_texto"])))
                if x.get("nota_ego_id"):
                    ids.add(x["nota_ego_id"])
        ini += 1000
        if len(l) < 1000:
            return ks, ids


def novas(desde: str = "") -> list[dict]:
    """Notas com texto das oportunidades ativas que ainda não estão em `notas` (só leitura)."""
    ativas = ego_api.oportunidades_ativas()
    nome_de = {o["id"]: o["name"] for o in ativas if o.get("name")}
    ks, ids = da_bd(set(nome_de.values()), desde)
    return so_na_api(notas_da_api(list(nome_de)), nome_de, ks, ids, desde)


def uma_por_oportunidade(novas_: list[dict]) -> tuple[list[dict], int]:
    """A mais antiga de cada oportunidade; as outras ficam para o cron seguinte (devolve quantas). Cada INSERT dispara o
    `extract-preferences` e N notas da mesma oportunidade em milissegundos correm em paralelo a reescrever as preferências."""
    por_ref: dict[str, dict] = {}
    for n in sorted(novas_, key=lambda x: (x["dia"], x["ego_id"])):
        por_ref.setdefault(n["ref"], n)
    return list(por_ref.values()), len(novas_) - len(por_ref)


def gravar(novas_: list[dict], origem: str = "manual") -> dict:
    """INSERT linha a linha (nunca upsert), uma oportunidade de cada vez; copia url/cliente_nome/tipo da oportunidade.
    Regista o resumo em `agente_sync_log` (desfaz-se por `nota_ego_id`) e propaga `contacto_id` no fim."""
    sb = get_supabase()
    refs = sorted({n["ref"] for n in novas_})
    opp = {}
    for i in range(0, len(refs), 100):
        for o in sb.table("oportunidades").select("oportunidade_ref,url,cliente_nome,tipo_oportunidade").in_("oportunidade_ref", refs[i:i + 100]).execute().data:
            opp[o["oportunidade_ref"]] = {k: v for k, v in o.items() if k != "oportunidade_ref" and v is not None}
    try:
        utilizadores = ego_api.utilizadores()
    except Exception as e:  # sem o mapa grava sem autor; nunca pára a volta
        logger.warning("notas: utilizadores do eGO indisponíveis (%s)", type(e).__name__)
        utilizadores = {}
    r = {"inseridas": 0, "ego_ids": [], "erros": {}, "sem_oportunidade": 0, "autor_desconhecido": 0, "tipo_desconhecido": 0}
    for n in sorted(novas_, key=lambda x: (x["ref"], x["dia"])):
        if n["ref"] not in opp:  # oportunidade criada hoje no eGO: o relatório das 03:37 ainda não a trouxe (FK); tenta-se na volta seguinte
            r["sem_oportunidade"] += 1
            continue
        try:
            sb.table("notas").insert({**opp.get(n["ref"], {}), **linha_de_nota(n, utilizadores)}).execute()
            r["inseridas"] += 1
            r["autor_desconhecido"] += n.get("user_id") not in utilizadores
            r["tipo_desconhecido"] += n.get("tipo_id") not in _TIPOS and n.get("tipo_id") not in (0, None)
            r["ego_ids"].append(n["ego_id"])
        except Exception as e:
            r["erros"][str(n["ego_id"])] = repr(e)[:200]
    sb.table("agente_sync_log").insert({"tipo": "egorealestate_notas_api", "origem": origem, "resumo": r}).execute()
    if r["inseridas"]:
        r["propagado"] = sb.rpc("propagar_contacto_id", {}).execute().data
    return r
