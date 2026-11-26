"""Visitas das oportunidades pela API do eGO (P2 de `docs/fases/api-a-substituir-scraper-acelerado-plano.md`).

`ListRealestateVisitFile` com `leadIds` e `applicationId` no corpo (sem o `applicationId` dá 401): 200 leads por pedido, ~0,5 s.
Medido a 26/11 contra o relatório (1 794 pares): campos diretos 99,8–100 %, interesse e pontos 98–99 %, responsável 96 %; a API tem
mais 881 visitas históricas que o relatório nunca gravou. `scripts/comparar_visitas_api_relatorio.py` repete a medição.
Só INSERT das visitas novas e UPDATE dos campos que a BD tem vazios: nunca se sobrescreve nem se apaga o que o relatório gravou.
"""

import logging

import httpx

from app.config import settings
from app.integrations import ego_api

logger = logging.getLogger(__name__)

# Tabelas de ids da API (opções da agência, não há endpoint: aprendidas a 26/11 cruzando 1 794 visitas com o relatório). Um id fora delas
# salta-se, como o relatório faz com as opções que já não aparecem (79 + 98 + 21 visitas): conta-se em `ids_desconhecidos`.
_INTERESSE = {2172: "Muito Interessado", 2173: "Interessado", 2174: "Pouco Interessado", 2175: "Não Interessado"}
_POSITIVOS = {3: "Boas áreas", 5: "Boa localização", 19852: "Vista Mar", 19853: "Garagem", 20923: "Potencial de negócio"}
_NEGATIVOS = {9: "Má condição/estado do imóvel", 10: "Divisões Pequenas", 19851: "Obras", 20288: "Localização", 20922: "investimento avultado"}
_SOBRE_NEGOCIO = {20: "Dá feedback mais tarde", 21: "Está a ver outros imoveis", 16791: "Necessita de crédito", 19856: "Precisa de vender?"}
_COLUNAS = ("visita_imovel_ref", "visita_data", "visita_anulada", "visita_interessado", "visita_cliente", "visita_imovel_proprietario",
            "visita_pontos_positivos", "visita_pontos_negativos", "visita_sobre_negocio", "visita_observacoes", "visita_responsavel")


def da_api(lead_ids: list[int], lote: int = 200) -> list[dict]:
    """Todas as visitas das oportunidades `lead_ids` (ids da API), em lotes de `lote`."""
    saida: list[dict] = []
    with httpx.Client(timeout=120, headers={"User-Agent": ego_api._UA}) as c:
        s = ego_api._sessao_valida(c)
        for i in range(0, len(lead_ids), lote):
            r = c.post(f"{settings.egoapi_base_url}/realestate/Realestate/ListRealestateVisitFile", params={"applicationId": s["application_id"]},
                       json={"leadIds": lead_ids[i:i + lote], "applicationId": s["application_id"]},
                       headers={"Authorization": f"Bearer {s['token']}"})
            r.raise_for_status()
            d = r.json()
            saida += d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
    return saida


def _nomes(ids, tabela: dict[int, str], desconhecidos: list) -> str | None:
    nomes = []
    for i in ids or []:
        if i in tabela:
            nomes.append(tabela[i])
        else:
            desconhecidos.append(i)
    return ", ".join(nomes) or None


def linha_de_visita(v: dict, ref_oportunidade: str, ref_imovel: str | None, utilizadores: dict[int, str], resp_oportunidade: str | None,
                    desconhecidos: list | None = None) -> dict:
    """Linha de `visitas` pela visita da API. Só os campos com valor (um `None` nunca apagaria o que há). Responsável: o utilizador da
    visita e, se já saiu do eGO, o da oportunidade (96 % contra o relatório)."""
    d = desconhecidos if desconhecidos is not None else []
    interesse = _INTERESSE.get(v.get("interested")) if v.get("interested") else None
    if v.get("interested") and not interesse:
        d.append(v["interested"])
    linha = {
        "visita_ref_ego": v["visitReference"], "oportunidade_ref": ref_oportunidade, "visita_imovel_ref": ref_imovel,
        "visita_data": (v.get("date") or "")[:10], "visita_anulada": "Sim" if v.get("cancelled") else "Não", "visita_interessado": interesse,
        "visita_cliente": v.get("potencialClientName"), "visita_imovel_proprietario": v.get("ownerName"),
        "visita_pontos_positivos": _nomes(v.get("positivePoints"), _POSITIVOS, d), "visita_pontos_negativos": _nomes(v.get("negativePoints"), _NEGATIVOS, d),
        "visita_sobre_negocio": _nomes(v.get("aboutBusiness"), _SOBRE_NEGOCIO, d), "visita_observacoes": (v.get("observations") or "").strip() or None,
        "visita_responsavel": utilizadores.get(v.get("securityUserId")) or resp_oportunidade,
    }
    return {k: x for k, x in linha.items() if x not in (None, "")}


def planear(api: list[dict], bd: dict[str, dict], refs_existentes: set[str], nome_de_lead: dict[int, str], ref_de_imovel: dict[int, str],
            utilizadores: dict[int, str], resp_oportunidade: dict[str, str]) -> dict:
    """Decide o que fazer, sem escrever: `novas` (INSERT), `completar` {visita_ref_ego: campos} (a BD tem-nos vazios, UPDATE só desses),
    e contagens (`divergentes` por coluna: a BD tem outro valor e fica como está)."""
    r = {"novas": [], "completar": {}, "divergentes": {}, "iguais": 0, "sem_oportunidade": 0, "ids_desconhecidos": 0}
    for v in api:
        ref = nome_de_lead.get(v.get("leadId"))
        if not v.get("visitReference") or not ref:
            continue
        if ref not in refs_existentes:  # a oportunidade ainda não está na BD (FK): fica para outra volta
            r["sem_oportunidade"] += 1
            continue
        desc: list = []
        linha = linha_de_visita(v, ref, ref_de_imovel.get(v.get("realestateId")) or None, utilizadores, resp_oportunidade.get(ref), desc)
        r["ids_desconhecidos"] += len(desc)
        atual = bd.get(v["visitReference"])
        if atual is None:
            r["novas"].append(linha)
            continue
        vazios = {c: linha[c] for c in _COLUNAS if c in linha and atual.get(c) in (None, "")}
        for c in _COLUNAS:
            if c in linha and atual.get(c) not in (None, "") and str(atual[c]).strip().lower() != str(linha[c]).strip().lower():
                r["divergentes"][c] = r["divergentes"].get(c, 0) + 1
        if vazios:
            r["completar"][v["visitReference"]] = vazios
        else:
            r["iguais"] += 1
    return r


def sincronizar(sb, dry: bool = True) -> dict:
    """Visitas das oportunidades ativas pela API → `visitas`. `dry` (ou `VISITAS_API_EGO` vazio) só conta. Nunca apaga."""
    ativas = ego_api.oportunidades_ativas()
    nome_de_lead = {o["id"]: o["name"] for o in ativas if o.get("name")}
    api = [v for v in da_api(list(nome_de_lead)) if v.get("leadId") in nome_de_lead]
    refs = sorted(set(nome_de_lead.values()))
    existentes, resp, bd = set(), {}, {}
    for i in range(0, len(refs), 200):
        for o in sb.table("oportunidades").select("oportunidade_ref,responsavel").in_("oportunidade_ref", refs[i:i + 200]).execute().data:
            existentes.add(o["oportunidade_ref"])
            if o.get("responsavel"):
                resp[o["oportunidade_ref"]] = o["responsavel"]
        for x in sb.table("visitas").select("*").in_("oportunidade_ref", refs[i:i + 200]).execute().data:
            bd[x["visita_ref_ego"]] = x
    ref_de_imovel = {x["id"]: (x.get("reference") or "").strip() for x in ego_api.todos_os_imoveis() if x.get("id")}
    p = planear(api, bd, existentes, nome_de_lead, ref_de_imovel, ego_api.utilizadores(), resp)
    r = {"api": len(api), "bd": len(bd), "novas": len(p["novas"]), "a_completar": len(p["completar"]), "iguais": p["iguais"],
         "divergentes": p["divergentes"], "sem_oportunidade": p["sem_oportunidade"], "ids_desconhecidos": p["ids_desconhecidos"]}
    gravar = not dry and bool(settings.visitas_api_ego)
    r["ligado"] = gravar
    if not gravar:
        return r
    r.update({"inseridas": 0, "completadas": 0, "erros": 0})
    for linha in p["novas"]:
        try:
            sb.table("visitas").insert(linha).execute()
            r["inseridas"] += 1
        except Exception as e:  # chave duplicada = o relatório chegou entretanto; só o código, a mensagem pode ter pessoas
            if getattr(e, "code", None) != "23505":
                r["erros"] += 1
                logger.warning("visitas: %s por gravar (%s)", linha["visita_ref_ego"], getattr(e, "code", type(e).__name__))
    for ref, campos in p["completar"].items():
        try:
            sb.table("visitas").update(campos).eq("visita_ref_ego", ref).execute()
            r["completadas"] += 1
        except Exception as e:
            r["erros"] += 1
            logger.warning("visitas: %s por completar (%s)", ref, getattr(e, "code", type(e).__name__))
    if r["inseridas"]:
        try:
            r["propagado"] = sb.rpc("propagar_contacto_id", {}).execute().data
        except Exception as e:
            logger.warning("visitas: propagar_contacto_id falhou (%s)", getattr(e, "code", type(e).__name__))
    return r
