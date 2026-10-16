"""Lead de compra da Meta sem resposta ao WhatsApp → lead no eGO (`docs/fases/lead-compra-para-ego-plano.md`).

Pedido do Miguel: se a pessoa não responde à Matilde em 2 h, um consultor tem de lhe ligar. O eGO atribui o
consultor sozinho (regra de entrega da agência); aqui só se cria a lead, uma vez por contacto.

Travão: `contactos.ego_lead_em` (0050). Só leads criadas depois de `LEAD_COMPRA_EGO_DESDE` — o histórico nunca.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.agents.broker.guards import normalizar_telefone
from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import ego_api

logger = logging.getLogger(__name__)

JANELA_HORAS = 2
LIMITE_POR_VOLTA = 20
_ORIGEM_INTERNET = 1
_SUBORIGEM_FACEBOOK_INSTAGRAM = 4001  # global, origem Internet
_TIPO_PEDIDO_DE_CONTACTO = 7
_MASTER_VENDA = 2  # a mesma das leads do portal

_COLUNAS = ("id,nome,telefone,telemovel,email,meta_lead_id,imovel_ref,ad_name,meta_form_name,criado_em,"
            "template_enviado_em,respondeu_em,contacto_humano_em,whatsapp_falhou_em")


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


def elegivel(linha: dict, agora: datetime) -> bool:
    """Sem resposta e sem consultor, e (número sem WhatsApp, ou template enviado há mais de 2 h)."""
    if linha.get("respondeu_em") or linha.get("contacto_humano_em") or linha.get("ego_lead_em"):
        return False
    if linha.get("whatsapp_falhou_em"):
        return True  # quem não tem WhatsApp é quem mais precisa de telefonema: sem esperar
    template = _dt(linha.get("template_enviado_em"))
    return bool(template and template <= agora - timedelta(hours=JANELA_HORAS))


def corpo_da_lead(linha: dict) -> dict:
    """Corpo de `InsertLead`. Sem a conversa: só o necessário para o consultor ligar."""
    obs = ["Lead de anúncio de compra (Meta) que não respondeu ao WhatsApp da Matilde."]
    if linha.get("imovel_ref"):
        obs.append(f"Imóvel de interesse: {linha['imovel_ref']}.")
    if linha.get("ad_name"):
        obs.append(f"Anúncio: {linha['ad_name']}.")
    if linha.get("whatsapp_falhou_em"):
        obs.append("O número não recebeu a mensagem (sem WhatsApp ou inativo).")
    return ego_api.corpo_de_lead(
        title="Lead Meta compra — sem resposta ao WhatsApp",
        name=linha.get("nome"),
        phone=normalizar_telefone(linha.get("telefone") or linha.get("telemovel")),
        email=linha.get("email"),
        observation=" ".join(obs),
        originId=_ORIGEM_INTERNET,
        subOriginId=_SUBORIGEM_FACEBOOK_INSTAGRAM,
        typeId=_TIPO_PEDIDO_DE_CONTACTO,
        masterLeadTypeId=_MASTER_VENDA,
        externalId=str(linha["meta_lead_id"]) if linha.get("meta_lead_id") else None,
    )


def _ja_tem_oportunidade(telefone: str | None) -> bool:
    """Oportunidade ativa com consultor para este número (espelho do eGO, atraso até ~1 dia)."""
    if not telefone or len(telefone) < 9:
        return False
    resp = (
        get_supabase().table("oportunidades").select("oportunidade_ref")
        .eq("oportunidade_estado", "Ativa").not_.is_("responsavel", "null")
        .ilike("cliente_telefone", f"%{telefone[-9:]}%").limit(1).execute()
    )
    return bool(resp.data)


def _candidatas(agora: datetime) -> list[dict]:
    resp = (
        get_supabase().table("contactos").select(_COLUNAS)
        .not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
        .is_("ego_lead_em", "null").gte("criado_em", settings.lead_compra_ego_desde)
        .order("criado_em").limit(200).execute()
    )
    return [l for l in resp.data or [] if elegivel(l, agora)][:LIMITE_POR_VOLTA]


def processar(agora: datetime | None = None) -> dict:
    """Uma volta do cron. Falha da API deixa a lead por marcar (a próxima volta repete)."""
    if not settings.lead_compra_ego_desde:
        return {"ativo": False}
    agora = agora or datetime.now(timezone.utc)
    contagem = {"ativo": True, "criadas": 0, "ja_existiam": 0, "erros": 0}
    for linha in _candidatas(agora):
        marca = {"ego_lead_em": agora.isoformat()}
        try:
            if _ja_tem_oportunidade(normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))):
                contagem["ja_existiam"] += 1
            else:
                marca["ego_lead_id"] = ego_api.inserir_lead(corpo_da_lead(linha))
                contagem["criadas"] += 1
            get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
        except Exception:
            logger.exception("Falha a enviar a lead %s para o eGO", linha["id"])
            contagem["erros"] += 1
    return contagem
