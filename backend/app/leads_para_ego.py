"""Lead de compra da Meta sem resposta ao WhatsApp → lead no eGO (`docs/fases/lead-compra-para-ego-plano.md`).

Pedido do Miguel: se a pessoa não responde à Matilde em 2 h, um consultor tem de lhe ligar. O eGO atribui o
consultor sozinho (regra de entrega da agência); aqui só se cria a lead, uma vez por contacto.
A criação usa a Web API (`PUT /v1/Lead`, a configuração antiga do Make) enquanto a API nova (`InsertLead`) não tem permissão.

Travão: `contactos.ego_lead_em` (0050). Só leads criadas depois de `LEAD_COMPRA_EGO_DESDE` — o histórico nunca.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.agents.broker.guards import normalizar_telefone
from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import ego_api, egorealestate

logger = logging.getLogger(__name__)

JANELA_HORAS = 2
LIMITE_POR_VOLTA = 20

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


def observacao_da_lead(linha: dict, com_imovel: bool, recusou: bool = False, ja_conhecido: bool = False) -> str:
    """Texto do campo OBS da lead no eGO. Sem a conversa."""
    obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads",
           "recusou o WhatsApp: contactar por telefone, nunca por WhatsApp." if recusou
           else "sem resposta ao WhatsApp da Matilde."]
    if ja_conhecido:
        obs.append("Contacto já existente no eGO.")
    if linha.get("imovel_ref") and not com_imovel:
        obs.append(f"Imóvel de interesse: {linha['imovel_ref']}.")
    if linha.get("whatsapp_falhou_em"):
        obs.append("O número não recebeu a mensagem (sem WhatsApp ou inativo).")
    return " ".join(obs)


def _ego_id_do_imovel(ref: str | None) -> int | None:
    """`imoveis.ego_id` = `RID` da Web API."""
    if not ref:
        return None
    resp = get_supabase().table("imoveis").select("ego_id").eq("imovel_ref", ref).limit(1).execute()
    return (resp.data[0].get("ego_id") if resp.data else None) or None


def _ja_nas_leads(linha: dict, leads: list[dict]) -> bool:
    """A pessoa já está na caixa de leads (o Miguel pôs lotes à mão): mesmo telefone ou email."""
    tel = normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))
    email = (linha.get("email") or "").strip().lower()
    return any(
        (tel and normalizar_telefone(l.get("phone")) == tel) or (email and (l.get("email") or "").strip().lower() == email)
        for l in leads
    )


def _responsavel_da_oportunidade(telefone: str | None, email: str | None = None) -> str | None:
    """Consultor de uma oportunidade ativa deste número ou email (espelho do eGO, atraso até ~1 dia)."""
    tabela = get_supabase().table("oportunidades")
    base = lambda: tabela.select("responsavel").eq("oportunidade_estado", "Ativa").not_.is_("responsavel", "null")  # noqa: E731
    if telefone and len(telefone) >= 9:
        r = base().ilike("cliente_telefone", f"%{telefone[-9:]}%").limit(1).execute().data
        if r:
            return r[0]["responsavel"]
    if email:
        r = base().ilike("cliente_email", email.strip()).limit(1).execute().data
        if r:
            return r[0]["responsavel"]
    return None


def _ja_tem_oportunidade(telefone: str | None) -> bool:
    return bool(_responsavel_da_oportunidade(telefone))


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
    candidatas = _candidatas(agora)
    if not candidatas:
        return contagem
    try:
        leads = ego_api.leads_abertas()  # sem saber o que lá está, criar podia duplicar: nesta volta não se cria
    except Exception:
        logger.exception("Falha a ler as leads do eGO — nenhuma lead criada nesta volta")
        return contagem | {"erros": len(candidatas)}
    for linha in candidatas:
        marca = {"ego_lead_em": agora.isoformat()}
        try:
            tel = normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))
            if _ja_nas_leads(linha, leads) or _ja_tem_oportunidade(tel):
                contagem["ja_existiam"] += 1
            else:
                ego_id = _ego_id_do_imovel(linha.get("imovel_ref"))
                ident = egorealestate.inserir_lead_webapi(
                    linha.get("nome") or "Lead Meta compra", linha.get("email"), tel,
                    observacao_da_lead(linha, bool(ego_id)), ego_id)
                if ident and ident.isdigit():
                    marca["ego_lead_id"] = int(ident)
                contagem["criadas"] += 1
            get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
        except Exception:
            logger.exception("Falha a enviar a lead %s para o eGO", linha["id"])
            contagem["erros"] += 1
    return contagem


def _email_do_responsavel(nome: str | None) -> str | None:
    if not nome:
        return None
    r = get_supabase().table("profiles").select("email").eq("ego_responsavel", nome).limit(1).execute().data
    return (r[0].get("email") if r else None) or None


def _contacto_conhecido(linha: dict, tel: str | None) -> bool:
    """Já há outro contacto do eGO com este telefone (`ego_link`): pessoa de uma campanha antiga."""
    if not tel or len(tel) < 9:
        return False
    r = (get_supabase().table("contactos").select("id").not_.is_("ego_link", "null")
         .ilike("telefone", f"%{tel[-9:]}%").neq("id", linha["id"]).limit(1).execute().data)
    return bool(r)


def _id_da_lead(tel: str | None, email: str | None) -> int | None:
    """Confirma na caixa de leads do eGO e devolve o id (o PUT da Web API pode não o devolver). Melhor esforço."""
    try:
        for l in ego_api.leads_abertas():
            if _ja_nas_leads({"telefone": tel, "email": email}, [l]) and str(l.get("id", "")).isdigit():
                return int(l["id"])
    except Exception:
        logger.warning("Não foi possível confirmar a lead no eGO", exc_info=True)
    return None


def recusou_whatsapp(meta_lead_id: str) -> dict | None:
    """Comprador que recusou o WhatsApp: tem de ficar no eGO já, sem esperar 2 h (chamado pelo n8n, a par do email).

    Quatro casos: (1) oportunidade ativa com consultor, não cria e devolve esse consultor para avisar; (2) já na caixa
    de leads, não cria; (3) contacto antigo ou (4) sem histórico, cria a lead. Se o eGO não responder à verificação,
    cria na mesma (perder a lead é pior que duplicá-la) e diz `verificado_no_ego: false`. Devolve `None` se o
    contacto não existe. Falha do PUT levanta: a lead fica por marcar e o n8n vê o erro."""
    linhas = (get_supabase().table("contactos").select(_COLUNAS + ",ego_lead_em")
              .eq("meta_lead_id", meta_lead_id).limit(1).execute().data)
    if not linhas:
        return None
    linha = linhas[0]
    if linha.get("ego_lead_em"):
        return {"resultado": "ja_tratada"}
    agora = datetime.now(timezone.utc)
    tel = normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))
    email = linha.get("email")

    try:
        na_caixa = _ja_nas_leads(linha, ego_api.leads_abertas())
        verificado = True
    except Exception:
        logger.exception("Falha a ler as leads do eGO — a criar sem confirmar")
        na_caixa, verificado = False, False

    responsavel = _responsavel_da_oportunidade(tel, email)
    marca = {"ego_lead_em": agora.isoformat()}
    if responsavel:
        resultado = "oportunidade_ativa"
    elif na_caixa:
        resultado = "ja_na_caixa"
    else:
        resultado = "criada"
        ego_id = _ego_id_do_imovel(linha.get("imovel_ref"))
        egorealestate.inserir_lead_webapi(
            linha.get("nome") or "Lead Meta compra", email, tel,
            observacao_da_lead(linha, bool(ego_id), recusou=True, ja_conhecido=_contacto_conhecido(linha, tel)), ego_id)
        id_lead = _id_da_lead(tel, email) if verificado else None
        if id_lead:
            marca["ego_lead_id"] = id_lead
    get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
    return {"resultado": resultado, "criada": resultado == "criada", "verificado_no_ego": verificado,
            "responsavel": responsavel, "email_responsavel": _email_do_responsavel(responsavel)}
