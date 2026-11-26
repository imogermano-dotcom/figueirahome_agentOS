"""Esqueleto das oportunidades do eGO que o relatório ainda não trouxe (pedido #28, `docs/fases/oportunidades-em-falta-pela-api-plano.md`).

O relatório das 03:37 só lê as oportunidades *editadas* nas últimas 48 h e criar uma não conta: a linha demora dias (ou nunca vem) e as
notas dessa oportunidade não entram (FK). Aqui cria-se só o que a lista de ativas da API dá. **Só INSERT**; o relatório completa o resto
(o upsert dele só escreve os campos que traz). Nunca escreve no eGO nem toca em linhas que existam.
"""

import logging
import re

from app.db.supabase_client import get_supabase
from app.integrations import ego_api

logger = logging.getLogger(__name__)

MAX_POR_VOLTA = 50
_URL = "https://admin.egorealestate.com/egocore/Leads/{}"
# Medidos a 26/11 em 2 648 oportunidades (API contra BD).
_TIPO_OPORTUNIDADE = {1: "Angariação", 2: "Venda", 3: "Arrendamento"}  # masterLeadType.id
_TIPO_PEDIDO = {4: "Pedido de Informação", 3: "Pedido de Visita", 1: "Procura", 7: "Pedido de Contacto"}  # leadTypeId; 0 = vazio
_ABERTA = (0, 1)  # leadStage: 0/1 = Ativa (o 0 era «Criada»); 2 = Ganha, 3 = Perdida (a lista de ativas também as traz)


def _pt(campo: dict | None) -> str | None:
    return ((campo or {}).get("nameMls") or {}).get("PT-PT")


def esqueleto(o: dict, utilizadores: dict[int, str], etapa: str | None = None, imovel: dict | None = None) -> dict | None:
    """Linha mínima para `oportunidades`, ou `None` se não se deve criar (fechada, tipo desconhecido, sem referência).
    `etapa` (`IsReport`) e `imovel` (a linha de `imoveis`: natureza, concelho, freguesia) só se conhecidos; preços, distrito e proprietário
    ficam para o relatório (os preços da oportunidade são os da altura e diferem dos do imóvel em 18 % das linhas)."""
    if not o.get("name") or o.get("leadStage") not in _ABERTA:
        return None
    tipo = _TIPO_OPORTUNIDADE.get((o.get("masterLeadType") or {}).get("id"))
    if not tipo:
        return None
    linha = {
        "oportunidade_ref": o["name"], "oportunidade_estado": "Ativa", "tipo_oportunidade": tipo,
        "tipo_pedido": _TIPO_PEDIDO.get(o.get("leadTypeId")),
        "cliente_nome": o.get("title"), "cliente_email": o.get("email"), "cliente_telefone": o.get("phone"),
        "ego_lead_id": o.get("id"), "url": _URL.format(o["id"]) if o.get("id") else None,
        "ego_data_criacao": (o.get("createDate") or "")[:10] or None, "data_criacao_iso": (o.get("createDate") or "")[:10] or None,
        "ego_editado_em": (o.get("alterDate") or "")[:10] or None, "imovel_ref": o.get("realestateReference"),
        "origem": _pt(o.get("leadOrigin")), "sub_origem": _pt(o.get("leadSubOrigin")),
        "responsavel": utilizadores.get(o.get("assignToSecurityUserId")), "etapa_atual": etapa,
        "imovel_natureza": (imovel or {}).get("natureza"), "imovel_concelho": (imovel or {}).get("concelho"),
        "imovel_freguesia": (imovel or {}).get("freguesia"),
    }
    return {k: v for k, v in linha.items() if v not in (None, "")}


def _digitos9(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")[-9:]


def _contacto_unico(sb, o: dict) -> tuple[str, str] | None:
    """(`contacto_id`, `contacto_match`) se o telefone ou, na falta, o email dão EXATAMENTE um contacto; com 2 ou mais não se adivinha."""
    tel = _digitos9(o.get("phone"))
    if len(tel) == 9:
        ids = {c["id"] for c in sb.table("contactos").select("id").or_(f"telefone.ilike.%{tel}%,telemovel.ilike.%{tel}%").limit(5).execute().data}
        if ids:
            return (next(iter(ids)), "telefone") if len(ids) == 1 else None
    email = (o.get("email") or "").strip().lower()
    if email:
        ids = {c["id"] for c in sb.table("contactos").select("id").ilike("email", email).limit(5).execute().data}
        if len(ids) == 1:
            return next(iter(ids)), "email"
    return None


def criar_em_falta(ativas: list[dict], gravar: bool) -> dict:
    """Cria o esqueleto das ativas do eGO que não estão em `oportunidades` (máx. `MAX_POR_VOLTA`). `gravar` falso só conta (`criaria`)."""
    nomes = [o["name"] for o in ativas if o.get("name")]
    if not nomes:
        return {"em_falta": 0}
    sb = get_supabase()
    existem: set[str] = set()
    for i in range(0, len(nomes), 300):
        existem |= {r["oportunidade_ref"] for r in sb.table("oportunidades").select("oportunidade_ref").in_("oportunidade_ref", nomes[i:i + 300]).execute().data}
    falta = [o for o in ativas if o.get("name") and o["name"] not in existem]
    if not falta:
        return {"em_falta": 0}
    try:
        utilizadores = ego_api.utilizadores()
    except Exception as e:  # sem o mapa cria sem responsável; o relatório completa-o
        logger.warning("oportunidades: utilizadores do eGO indisponíveis (%s)", type(e).__name__)
        utilizadores = {}
    try:  # a etapa vem de outra lista da API; sem ela cria sem etapa e o relatório completa
        etapas = ego_api.etapas_ativas()
    except Exception as e:
        logger.warning("oportunidades: etapas do eGO indisponíveis (%s)", type(e).__name__)
        etapas = {}
    imoveis: dict[str, dict] = {}
    refs_im = sorted({o["realestateReference"] for o in falta if o.get("realestateReference")})
    for i in range(0, len(refs_im), 300):
        try:
            imoveis |= {x["imovel_ref"]: x for x in sb.table("imoveis").select("imovel_ref,natureza,concelho,freguesia").in_("imovel_ref", refs_im[i:i + 300]).execute().data}
        except Exception as e:
            logger.warning("oportunidades: imóveis por ler (%s)", getattr(e, "code", type(e).__name__))
    prontas = [(o, esqueleto(o, utilizadores, etapas.get(o["name"]), imoveis.get(o.get("realestateReference")))) for o in falta]
    r = {"em_falta": len(falta), "saltadas": sum(1 for _, e in prontas if e is None)}
    prontas = [(o, e) for o, e in prontas if e][:MAX_POR_VOLTA]
    r["com_etapa"] = sum(1 for _, e in prontas if e.get("etapa_atual"))
    r["com_imovel"] = sum(1 for _, e in prontas if e.get("imovel_concelho"))
    if not gravar:
        r["criaria"] = len(prontas)
        return r
    r.update({"criadas": 0, "erros": 0, "ligadas": 0})
    pares = []
    for o, e in prontas:
        try:
            sb.table("oportunidades").insert(e).execute()
            r["criadas"] += 1
        except Exception as ex:  # chave duplicada = o relatório chegou entretanto: não é erro; só o código, a mensagem pode ter pessoas
            if getattr(ex, "code", None) != "23505":
                r["erros"] += 1
                logger.warning("oportunidades: esqueleto de %s falhou (%s)", e["oportunidade_ref"], getattr(ex, "code", type(ex).__name__))
            continue
        try:
            if par := _contacto_unico(sb, o):
                pares.append({"oportunidade_ref": e["oportunidade_ref"], "contacto_id": par[0], "contacto_match": par[1]})
        except Exception as ex:
            logger.warning("oportunidades: contacto de %s por ligar (%s)", e["oportunidade_ref"], getattr(ex, "code", type(ex).__name__))
    if pares:
        try:
            sb.rpc("set_contacto_oportunidades", {"pares": pares}).execute()  # também propaga às notas, tarefas e visitas
            r["ligadas"] = len(pares)
        except Exception as ex:
            logger.warning("oportunidades: RPC set_contacto_oportunidades falhou (%s)", getattr(ex, "code", type(ex).__name__))
    return r
