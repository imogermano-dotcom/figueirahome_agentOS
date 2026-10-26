"""Lead de compra da Meta sem resposta ao WhatsApp → lead no eGO (`docs/fases/lead-compra-para-ego-plano.md`).

Pedido do Miguel: se a pessoa não responde à Matilde em 2 h, um consultor tem de lhe ligar. O eGO atribui o
consultor sozinho (regra de entrega da agência); aqui só se cria a lead, uma vez por contacto.
A criação usa a Web API (`PUT /v1/Lead`, a configuração antiga do Make) enquanto a API nova (`InsertLead`) não tem permissão.

Travão: `contactos.ego_lead_em` (0050). Só leads criadas depois de `LEAD_COMPRA_EGO_DESDE` — o histórico nunca.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.agents.broker.guards import normalizar_telefone
from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import ego_api, egorealestate

logger = logging.getLogger(__name__)

JANELA_HORAS = 2
HORA_ABRE, HORA_FECHA = 9, 20  # o cron só cria leads das 9h às 20h de Lisboa: uma lead das 23h espera pelas 9h (a consultora só liga de dia)
LIMITE_POR_VOLTA = 20
# Convenção do Miguel nas leads da campanha que pôs à mão a 17/10 (ids da agência 6429, não são segredo), usada pelo
# caminho `api` (InsertLead). A Web API põe sempre origem Internet / «www.figueirahome.com» (como as leads do site).
_ORIGEM_OUTROS = 11
_SUBORIGEM_FACEBOOK_CAMPANHA = 34798477
_TIPO_PEDIDO_DE_INFORMACAO = 4
_MASTER_VENDA = 2
_MAX_RESUMO_OBS = 600  # do resumo da conversa que vai no OBS da lead

_COLUNAS = ("id,nome,telefone,telemovel,email,meta_lead_id,imovel_ref,ad_name,meta_form_name,criado_em,"
            "meta_created_at,template_enviado_em,respondeu_em,contacto_humano_em,whatsapp_falhou_em,"
            "interesse_real_em,interesse_real_motivo,interesse_real_resumo")


def dentro_do_horario(agora: datetime) -> bool:
    """Das 9h às 20h, hora de Lisboa. Não vale para a recusa do WhatsApp, que vai logo (n8n)."""
    return HORA_ABRE <= agora.astimezone(ZoneInfo("Europe/Lisbon")).hour < HORA_FECHA


def entrou_pela_meta_em(linha: dict) -> str:
    """Dia (AAAA-MM-DD) em que a lead Meta entrou. É `meta_created_at`, não `contactos.criado_em`: quando a pessoa já existia no
    eGO (contacto antigo), a lead Meta reaproveita a linha e o `criado_em` fica na data original, o que a excluía de tudo
    (26/10: um comprador de 14/08 escalado com interesse real nunca era apanhado). `criado_em` só como último recurso."""
    return str(linha.get("meta_created_at") or linha.get("criado_em") or "")[:10]


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
    if linha.get("interesse_real_em"):  # pedido #17: respondeu à Matilde e mostrou interesse
        resumo = " ".join((linha.get("interesse_real_resumo") or "").split())[:_MAX_RESUMO_OBS]
        quando = (f"respondeu à Matilde com interesse real ({linha['interesse_real_motivo']})."
                  if linha.get("interesse_real_motivo") else "respondeu à Matilde com interesse real.")
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads", quando,
               f"Resumo: {resumo}" if resumo else "", "Contactar por telefone ou WhatsApp."]
        obs = [o for o in obs if o]
    else:
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


class SemConsultora(Exception):
    """Sem imóvel (ou sem responsável no eGO) a lead ficaria sem consultora: criada mas invisível para todos."""


def ref_do_anuncio(ad_name: str | None) -> str | None:
    """«FH2584_V1» → «FH2584»: os anúncios chamam-se pela referência do imóvel."""
    m = re.match(r"\s*(FH\d+[A-Z]?)(?![A-Za-z0-9])", ad_name or "", re.I)
    return m.group(1).upper() if m else None


def corpo_insert_lead(linha: dict, tel: str | None, observacao: str, imovel_id: int | None, consultor_id: int | None) -> dict:
    """Corpo do `InsertLead`. Sem `assignToSecurityUserId` a lead fica invisível (teste de 21/10, outra agência), por isso
    vai atribuída à consultora do imóvel (`securityUserId` do imóvel). `typeId`, não `leadTypeId` (esse é ignorado)."""
    nome = linha.get("nome") or "Lead Meta compra"
    atribuicao = ({"assignToSecurityUserId": consultor_id, "assignToSecurityUserIDList": [consultor_id]}
                  if consultor_id else {})
    return ego_api.corpo_de_lead(
        title=nome, name=nome, phone=tel, email=linha.get("email"), observation=observacao,
        originId=_ORIGEM_OUTROS, subOriginId=_SUBORIGEM_FACEBOOK_CAMPANHA, typeId=_TIPO_PEDIDO_DE_INFORMACAO,
        masterLeadTypeId=_MASTER_VENDA, realestateId=imovel_id, **atribuicao)


def _consultor_do_imovel(im: dict | None) -> int | None:
    """Consultora responsável pelo imóvel no eGO: `assignToSecurityUserId`; se o imóvel não a tiver, `securityUserId`.
    ⚠️ `securityUserId` sozinho é QUEM CRIOU o registo: no FH2584 era outra pessoa e a lead de teste de 21/10 foi
    atribuída a quem não devia (o responsável era o Miguel). Medido em 3 imóveis contra o `angariador`."""
    if not im:
        return None
    return im.get("assignToSecurityUserId") or im.get("securityUserId") or None


def _criar_lead(linha: dict, tel: str | None, recusou: bool = False, ja_conhecido: bool = False) -> int | None:
    """Cria a lead no eGO pelo caminho de `EGO_CRIAR_LEAD_POR` e devolve o id se o caminho o der (a Web API não o dá).
    Levanta se o eGO recusar: a lead fica por marcar."""
    ref = linha.get("imovel_ref")
    if settings.ego_criar_lead_por == "api":
        im = ego_api.imovel(ref) if ref else None
        obs = observacao_da_lead(linha, bool(im), recusou, ja_conhecido)
        consultor = _consultor_do_imovel(im)
        if not consultor:  # nunca criar uma lead que ninguém vê (21/10: a de um comprador que recusou ficou sem imóvel nem consultora)
            raise SemConsultora(f"imóvel {ref or '—'} sem responsável no eGO")
        return ego_api.inserir_lead(corpo_insert_lead(linha, tel, obs, (im or {}).get("id"), consultor))
    ego_id = _ego_id_do_imovel(ref)
    ident = egorealestate.inserir_lead_webapi(
        linha.get("nome") or "Lead Meta compra", linha.get("email"), tel,
        observacao_da_lead(linha, bool(ego_id), recusou, ja_conhecido), ego_id)
    return int(ident) if ident and str(ident).isdigit() else None


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
        .is_("ego_lead_em", "null").gte("meta_created_at", settings.lead_compra_ego_desde)
        .order("meta_created_at").limit(200).execute()
    )
    return [l for l in resp.data or [] if elegivel(l, agora)][:LIMITE_POR_VOLTA]


def _candidatas_interesse() -> list[dict]:
    """Compradores Meta marcados com interesse real (pedido #17), **mesmo os que já responderam**. Desligado sem o segredo."""
    if not settings.lead_interesse_ego:
        return []
    resp = (
        get_supabase().table("contactos").select(_COLUNAS)
        .not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
        .not_.is_("interesse_real_em", "null").is_("ego_lead_em", "null")
        .gte("meta_created_at", settings.lead_compra_ego_desde).order("interesse_real_em").limit(LIMITE_POR_VOLTA).execute()
    )
    return [l for l in resp.data or [] if not l.get("ego_lead_em")]


def processar(agora: datetime | None = None) -> dict:
    """Uma volta do cron. Falha da API deixa a lead por marcar (a próxima volta repete)."""
    if not settings.lead_compra_ego_desde:
        return {"ativo": False}
    agora = agora or datetime.now(timezone.utc)
    if not dentro_do_horario(agora):
        return {"ativo": True, "fora_do_horario": True}
    contagem = {"ativo": True, "criadas": 0, "ja_existiam": 0, "erros": 0}
    candidatas = _candidatas(agora)
    vistas = {l["id"] for l in candidatas}
    candidatas += [l for l in _candidatas_interesse() if l["id"] not in vistas]
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
            elif not (linha.get("email") or "").strip():  # a Web API recusa sem email: fica por criar, à vista
                logger.warning("Lead %s sem email: não se cria no eGO (Web API exige)", linha["id"])
                contagem["erros"] += 1
                continue
            else:
                ident = _criar_lead(linha, tel) or _id_da_lead(tel, linha.get("email"))  # a Web API não devolve o id
                if ident:
                    marca["ego_lead_id"] = ident
                contagem["criadas"] += 1
            get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
        except SemConsultora as e:
            logger.warning("Lead %s não criada: %s", linha["id"], e)
            contagem["erros"] += 1
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


def recusou_whatsapp(meta_lead_id: str, imovel_ref: str | None = None) -> dict | None:
    """Comprador que recusou o WhatsApp: tem de ficar no eGO já, sem esperar 2 h (chamado pelo n8n, a par do email).

    Quatro casos: (1) oportunidade ativa com consultor, não cria e devolve esse consultor para avisar; (2) já na caixa
    de leads, não cria; (3) contacto antigo ou (4) sem histórico, cria a lead. Se o eGO não responder à verificação,
    cria na mesma (perder a lead é pior que duplicá-la) e diz `verificado_no_ego: false`. Devolve `None` se o
    contacto não existe. Falha do PUT levanta: a lead fica por marcar e o n8n vê o erro.
    Desligado com `LEAD_COMPRA_EGO_DESDE` vazio, e nunca para contactos anteriores a essa data (o histórico não)."""
    if not settings.lead_compra_ego_desde:
        return {"resultado": "desligado", "criada": False}
    linhas = (get_supabase().table("contactos").select(_COLUNAS + ",ego_lead_em")
              .eq("meta_lead_id", meta_lead_id).limit(1).execute().data)
    if not linhas:
        return None
    linha = linhas[0]
    if linha.get("ego_lead_em"):
        return {"resultado": "ja_tratada"}
    # compara-se por dia (a data de ativação é um dia) e pela entrada da lead Meta, não pelo `criado_em` do contacto
    if entrou_pela_meta_em(linha) < str(settings.lead_compra_ego_desde)[:10]:
        return {"resultado": "anterior_a_ativacao", "criada": False}
    agora = datetime.now(timezone.utc)
    tel = normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))
    email = linha.get("email")
    # o RPC da compra não grava `imovel_ref` em `contactos` para quem recusa: vem do n8n, ou do nome do anúncio
    linha["imovel_ref"] = linha.get("imovel_ref") or (imovel_ref or "").strip() or ref_do_anuncio(linha.get("ad_name"))

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
    elif not (email or "").strip():
        # a Web API devolve 400 sem email (teste de 20/10); os formulários da Meta obrigam a pô-lo, por isso é raro
        return {"resultado": "sem_email", "criada": False, "verificado_no_ego": verificado, "responsavel": None,
                "email_responsavel": None}
    else:
        resultado = "criada"
        try:
            id_lead = _criar_lead(linha, tel, recusou=True, ja_conhecido=_contacto_conhecido(linha, tel))
        except SemConsultora as e:  # não marca: o email diz para criar à mão
            logger.warning("Recusa %s: lead não criada (%s)", linha["id"], e)
            return {"resultado": "sem_consultora", "criada": False, "verificado_no_ego": verificado,
                    "responsavel": None, "email_responsavel": None}
        if not id_lead and verificado:  # a Web API não devolve o id: apanha-se na caixa do eGO (melhor esforço)
            id_lead = _id_da_lead(tel, email)
        if id_lead:
            marca["ego_lead_id"] = id_lead
    if linha.get("imovel_ref"):
        marca["imovel_ref"] = linha["imovel_ref"]  # fica para os follow-ups e para quem ler o contacto
    get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
    return {"resultado": resultado, "criada": resultado == "criada", "verificado_no_ego": verificado,
            "responsavel": responsavel, "email_responsavel": _email_do_responsavel(responsavel)}
