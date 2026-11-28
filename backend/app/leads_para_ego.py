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

from app.agents.broker.guards import (
    _TAREFA_QUALIFICADA, e_fecho_da_pessoa, e_fora_do_alcance, e_mensagem_pre_preenchida, e_recusa, normalizar_telefone, vale_para_a_entrada,
    variantes_telefone,
)
from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import ego_api, egorealestate
from app.notificacoes import notificar

logger = logging.getLogger(__name__)

JANELA_HORAS = 2
HORA_ABRE, HORA_FECHA = 9, 20  # só o nudge o usa: desde 04/11 o cron cria leads a qualquer hora (a rede do portal, que as criava de noite, vai ser desligada)
LIMITE_POR_VOLTA = 20
# Convenção do Miguel nas leads da campanha que pôs à mão a 17/10 (ids da agência 6429, não são segredo), usada pelo
# caminho `api` (InsertLead). A Web API põe sempre origem Internet / «www.figueirahome.com» (como as leads do site).
_ORIGEM_OUTROS = 11
_SUBORIGEM_FACEBOOK_CAMPANHA = 34798477
_TIPO_PEDIDO_DE_INFORMACAO = 4
_MASTER_VENDA = 2
_MAX_RESUMO_OBS = 600  # do resumo da conversa que vai no OBS da lead
_MAX_RESPOSTAS_OBS = 900  # do bloco «Respostas da pessoa» (as mais recentes; o pedido inicial fica sempre)
_PERGUNTA_OBS, _RESPOSTA_OBS = 140, 200  # por pergunta da Matilde e por resposta da pessoa
IDADE_MAX_PARADA_DIAS = 14  # só se olha para as que entraram há menos tempo (cada uma custa uma consulta por volta)
IDADE_MAX_REENTRADA_DIAS = 7  # uma pessoa que volta (linha de `contactos` reaproveitada) só conta se a entrada nova for recente
LEAD_NOVA_MAX_POR_DIA_H = 24  # no máximo uma lead nova por pessoa neste intervalo (a consultora pode voltar a converter)
JANELA_PARADA_HORAS = 2  # conversa sem mensagens (nem o lembrete) há este tempo: a pessoa já não vai responder (24/11: após 2 h só 14 % voltam, após 4 h 9 %)

_COLUNAS = ("id,nome,telefone,telemovel,email,meta_lead_id,imovel_ref,ad_name,meta_form_name,criado_em,"
            "meta_created_at,template_enviado_em,respondeu_em,contacto_humano_em,whatsapp_falhou_em,"
            "interesse_real_em,interesse_real_motivo,interesse_real_resumo,nao_contactar_em,ego_lead_em")


def dentro_do_horario(agora: datetime) -> bool:
    """Das 9h às 20h, hora de Lisboa. Só o nudge o respeita; a criação de leads no eGO já não."""
    return HORA_ABRE <= agora.astimezone(ZoneInfo("Europe/Lisbon")).hour < HORA_FECHA


def registar_marcas(via: str, agora: datetime, ids: list, **extra) -> None:
    """Deixa em `agente_sync_log` a hora (UTC e de Lisboa) a que se marcaram leads: a 04/11 apareceram 8 criações às 07:20 UTC,
    fora das 9h–20h, e os logs do Fly já não chegavam lá. Nunca levanta."""
    try:
        resumo = {"via": via, "agora_utc": agora.isoformat(), "hora_lisboa": agora.astimezone(ZoneInfo("Europe/Lisbon")).isoformat(),
                  "dentro_do_horario": dentro_do_horario(agora), "contactos": [str(i) for i in ids], **extra}
        get_supabase().table("agente_sync_log").insert({"tipo": "leads_para_ego", "resumo": resumo, "origem": "cron" if via in ("cron", "respondeu_depois") else "n8n"}).execute()
    except Exception:
        logger.exception("Falha a registar as marcas de leads_para_ego")


def entrou_pela_meta_em(linha: dict) -> str:
    """Dia (AAAA-MM-DD) em que a lead Meta entrou. É `meta_created_at`, não `contactos.criado_em`: quando a pessoa já existia no
    eGO (contacto antigo), a lead Meta reaproveita a linha e o `criado_em` fica na data original, o que a excluía de tudo
    (26/10: um comprador de 14/08 escalado com interesse real nunca era apanhado). `criado_em` só como último recurso."""
    return str(linha.get("meta_created_at") or linha.get("criado_em") or "")[:10]


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


def precisa_de_lead(linha: dict, agora: datetime) -> bool:
    """Falta criar a lead desta entrada. Uma marca desta entrada (ou sem como a datar) trava. Uma **reentrada** (rasto de
    entrada anterior: marca, template, resposta…) só conta se a entrada nova for dos últimos `IDADE_MAX_REENTRADA_DIAS`:
    o histórico não se recupera (22/11: uma entrada de 07/11 com `respondeu_em` de outubro passava a candidata)."""
    if linha.get("ego_lead_em") and vale_para_a_entrada(linha, "ego_lead_em"):
        return False
    if not _reentrada(linha):
        return True
    entrada = _dt(linha.get("meta_created_at"))
    return bool(entrada and entrada >= agora - timedelta(days=IDADE_MAX_REENTRADA_DIAS))


def _reentrada(linha: dict) -> bool:
    """A linha traz o rasto de uma entrada anterior (algum destes campos é anterior a `meta_created_at`)."""
    entrada = _dt(linha.get("meta_created_at"))
    return bool(entrada) and any(
        (v := _dt(linha.get(c))) and v < entrada
        for c in ("ego_lead_em", "template_enviado_em", "respondeu_em", "contacto_humano_em", "interesse_real_em"))


def _imovel_da_entrada(linha: dict) -> dict:
    """Numa reentrada `contactos.imovel_ref` é o da 1.ª entrada (o RPC só grava o novo em `leads`): usa-se o da linha de
    `leads` com o `meta_lead_id` atual. Sem ela, fica o que vinha. Nunca levanta."""
    if not (_reentrada(linha) and linha.get("meta_lead_id")):
        return linha
    try:
        r = get_supabase().table("leads").select("imovel_ref").eq("meta_lead_id", linha["meta_lead_id"]).limit(1).execute().data
    except Exception:
        logger.exception("Falha a ler o imóvel da entrada da lead %s", linha.get("id"))
        return linha
    return linha | {"imovel_ref": r[0]["imovel_ref"]} if r and r[0].get("imovel_ref") else linha


def elegivel(linha: dict, agora: datetime) -> bool:
    """Sem resposta e sem consultor, e (número sem WhatsApp, ou template enviado há mais de 2 h). `nao_contactar_em` não conta: é só do WhatsApp, a lead continua válida para o telefone.

    Só contam as marcas desta entrada, e as 2 h contam desde o último de template e entrada: numa reentrada o template é o
    da 1.ª vez e a pessoa ainda não teve tempo de escrever."""
    if any(vale_para_a_entrada(linha, c) for c in ("respondeu_em", "contacto_humano_em", "ego_lead_em")):
        return False
    if linha.get("whatsapp_falhou_em"):
        return True  # quem não tem WhatsApp é quem mais precisa de telefonema: sem esperar
    template = _dt(linha.get("template_enviado_em"))
    if not template:
        return False
    return max(template, _dt(linha.get("meta_created_at")) or template) <= agora - timedelta(hours=JANELA_HORAS)


def observacao_da_lead(linha: dict, com_imovel: bool, recusou: bool = False, ja_conhecido: bool = False) -> str:
    """Texto do campo OBS da lead no eGO. Sem a conversa."""
    if linha.get("voltou_a_responder"):  # lead nova: a anterior já foi tratada (convertida, arquivada ou apagada)
        anterior = f" (oportunidade {linha['oportunidade_anterior']})" if linha.get("oportunidade_anterior") else ""
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads",
               f"voltou a responder à Matilde depois de a lead anterior ser tratada{anterior}.", "Contactar por telefone ou WhatsApp."]
    elif vale_para_a_entrada(linha, "interesse_real_em"):  # pedido #17: respondeu à Matilde e mostrou interesse (desta entrada: o de outra é de outro imóvel)
        resumo = " ".join((linha.get("interesse_real_resumo") or "").split())[:_MAX_RESUMO_OBS]
        quando = (f"respondeu à Matilde com interesse real ({linha['interesse_real_motivo']})."
                  if linha.get("interesse_real_motivo") else "respondeu à Matilde com interesse real.")
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads", quando,
               f"Resumo: {resumo}" if resumo else "", "Contactar por telefone ou WhatsApp."]
        obs = [o for o in obs if o]
    elif "conversa_parada_resumo" in linha:  # respondeu à Matilde, mas a conversa parou sem sinal de interesse
        resumo = linha["conversa_parada_resumo"]
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads",
               "respondeu à Matilde mas a conversa parou sem pedido de visita.",
               f"Disse: {resumo}" if resumo else "", "Contactar por telefone ou WhatsApp."]
        obs = [o for o in obs if o]
    elif linha.get("acabou_de_entrar"):  # criada à entrada (pedido #17, 27/11): ainda não há conversa
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads",
               "acabou de entrar: a Matilde vai contactá-la por WhatsApp (ainda sem conversa)."]
    else:
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads",
               "recusou o WhatsApp: contactar por telefone, nunca por WhatsApp." if recusou
               else "sem resposta ao WhatsApp da Matilde."]
    if linha.get("procura_arrendar"):
        obs.insert(2, AVISO_ARRENDAR)
    if linha.get("respostas_da_pessoa"):
        obs.append(f"Respostas da pessoa: {linha['respostas_da_pessoa']}")
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


def telefone_da_linha(linha: dict) -> str | None:
    """Primeiro número utilizável de `telefone` e `telemovel` (o eGO guarda listas «a, b»; fichas antigas têm dois
    números colados ou o mesmo duas vezes, 18 dígitos). Sem nenhum válido recua ao comportamento antigo.
    ponytail: 10-15 dígitos aceita-se como estrangeiro; só sabe de PT (9 dígitos) e do tamanho E.164."""
    for campo in ("telefone", "telemovel"):
        for parte in re.split(r"[,;/]", linha.get(campo) or ""):
            n = normalizar_telefone(parte)
            if n and (len(n) == 9 or (10 <= len(n) <= 15 and n[: len(n) // 2] != n[len(n) // 2:])):
                return n
    return normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))


def _ja_nas_leads(linha: dict, leads: list[dict]) -> bool:
    """A pessoa já está na caixa de leads (o Miguel pôs lotes à mão): mesmo telefone ou email."""
    tel = telefone_da_linha(linha)
    email = (linha.get("email") or "").strip().lower()
    return any(
        (tel and normalizar_telefone(l.get("phone")) == tel) or (email and (l.get("email") or "").strip().lower() == email)
        for l in leads
    )


def _responsavel_da_oportunidade(telefone: str | None, email: str | None = None) -> str | None:
    """Consultor de uma oportunidade ativa deste número ou email (espelho do eGO, atraso até ~1 dia)."""
    tabela = get_supabase().table("oportunidades")
    base = lambda: (tabela.select("responsavel").eq("oportunidade_estado", "Ativa").eq("apagada_no_ego", False)  # noqa: E731
                    .not_.is_("responsavel", "null"))  # uma apagada no eGO não é uma oportunidade ativa (pedido #31)
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


def _ref_base(ref: str | None) -> str:
    """«FH2588_V1» e «FH2588A» → «FH2588»: o mesmo imóvel com sufixo de anúncio ou de lote."""
    m = re.match(r"[A-Za-z]*[0-9]+", ref or "")
    return m.group(0).upper() if m else (ref or "").strip().upper()


def _oportunidades_ativas(telefone: str | None, email: str | None = None) -> list[dict]:
    """Oportunidades ativas (não apagadas) deste número ou email: ref, imóvel e consultor."""
    def _q():
        return (get_supabase().table("oportunidades").select("oportunidade_ref,imovel_ref,responsavel")
                .eq("oportunidade_estado", "Ativa").eq("apagada_no_ego", False))
    r = []
    if telefone and len(telefone) >= 9:
        r = _q().ilike("cliente_telefone", f"%{telefone[-9:]}%").limit(10).execute().data or []
    if not r and email:
        r = _q().ilike("cliente_email", email.strip()).limit(10).execute().data or []
    return r


def _mesmo_imovel(ops: list[dict], ref: str | None) -> bool:
    """A pessoa já tem oportunidade ativa DESTE imóvel (ou não dá para provar que é de outro: sem ref de um dos lados)."""
    return not ref or any(not o.get("imovel_ref") or _ref_base(o["imovel_ref"]) == _ref_base(ref) for o in ops)


def _mesmo_imovel_da_lead(lead: dict, ref: str | None) -> bool:
    """A lead da caixa é deste imóvel (ou não dá para provar que é de outro: sem ref de um dos lados)."""
    ref_lead = lead.get("realestateReference")
    return not ref or not ref_lead or _ref_base(ref_lead) == _ref_base(ref)


def _lead_da_caixa(linha: dict, leads: list[dict]) -> dict | None:
    """Lead aberta desta pessoa PARA ESTE IMÓVEL. Uma de outro imóvel não conta: é interesse novo (13/11: o cron
    marcava-a como «já existia» e a lead do imóvel novo nunca chegava ao eGO)."""
    return next((l for l in leads if _ja_nas_leads(linha, [l]) and _mesmo_imovel_da_lead(l, linha.get("imovel_ref"))), None)


def _responsavel_do_mesmo_imovel(telefone: str | None, email: str | None, ref: str | None) -> str | None:
    """`_responsavel_da_oportunidade`, mas só se a oportunidade ativa for deste imóvel: uma de outro não trava a lead nova."""
    responsavel = _responsavel_da_oportunidade(telefone, email)
    if responsavel:
        ops = _oportunidades_ativas(telefone, email)
        if ops and not _mesmo_imovel(ops, ref):
            return None
    return responsavel


def _avisar_lead_na_caixa(linha: dict, lead: dict) -> None:
    """A pessoa já tem lead aberta deste imóvel no eGO, por isso não se cria outra. Avisa a consultora do imóvel (e o
    diretor) com o id da lead que fez match: antes marcava-se em silêncio e ninguém sabia que ela voltou. Nunca levanta."""
    try:
        motivo = linha.get("interesse_real_motivo") or ("respondeu à Matilde" if linha.get("respondeu_em") else "sem resposta ao WhatsApp há mais de 2 h")
        corpo = "\n".join((
            f"{linha.get('nome') or 'Uma pessoa'} entrou como lead da Meta pelo imóvel {linha.get('imovel_ref') or '—'}: {motivo}.",
            f"Telefone: {telefone_da_linha(linha) or '—'} · Email: {linha.get('email') or '—'}",
            f"Já há uma lead aberta no eGO com este contacto (id {lead.get('id') or '?'}, imóvel {lead.get('realestateReference') or '—'}).",
            "",
            "Não se criou lead nova (evita duplicar). Confirma que a lead existente é desta pessoa e acrescenta uma nota se for preciso.",
        ))
        notificar(f"Lead Meta já na caixa do eGO — {linha.get('imovel_ref') or 'imóvel?'}", corpo, imovel_ref=linha.get("imovel_ref"))
    except Exception:
        logger.exception("Falha a avisar da lead na caixa da lead %s", linha.get("id"))


def _avisar_oportunidade_ativa(linha: dict, ops: list[dict]) -> None:
    """Pedido #17 (10/11): a pessoa já tem oportunidade ativa deste imóvel, por isso não se cria lead nova; avisa-se a
    consultora (e o diretor). Antes marcava-se em silêncio e ninguém sabia que ela tinha voltado a mostrar interesse. Nunca levanta."""
    try:
        emails = [e for e in {_email_do_responsavel(o.get("responsavel")) for o in ops} if e]
        motivo = linha.get("interesse_real_motivo") or ("respondeu à Matilde" if linha.get("respondeu_em") else "sem resposta ao WhatsApp há mais de 2 h")
        resumo = " ".join((linha.get("interesse_real_resumo") or "").split())[:_MAX_RESUMO_OBS]
        corpo = "\n".join(p for p in (
            f"{linha.get('nome') or 'Uma pessoa'} voltou a mostrar interesse pelo imóvel {linha.get('imovel_ref') or '—'} (lead da Meta): {motivo}.",
            f"Telefone: {telefone_da_linha(linha) or '—'} · Email: {linha.get('email') or '—'}",
            "Já tem oportunidade ativa no eGO: " + ", ".join(sorted({o.get("oportunidade_ref") or "?" for o in ops})) + ".",
            f"Resumo: {resumo}" if resumo else None,
            "",
            "Não se criou lead nova (evita duplicar). Se quiseres, acrescenta uma nota na oportunidade.",
        ) if p is not None)
        notificar(f"Lead Meta com oportunidade ativa — {linha.get('imovel_ref') or 'imóvel?'}", corpo, para_extra=emails)
    except Exception:
        logger.exception("Falha a avisar da oportunidade ativa da lead %s", linha.get("id"))


def _sem_marca_ou_reentrada(agora: datetime) -> str:
    """Filtro do servidor (o PostgREST não compara duas colunas): sem marca, ou entrada recente (`precisa_de_lead` decide)."""
    return f"ego_lead_em.is.null,meta_created_at.gte.{(agora - timedelta(days=IDADE_MAX_REENTRADA_DIAS)).isoformat()}"


def _candidatas(agora: datetime) -> list[dict]:
    resp = (
        get_supabase().table("contactos").select(_COLUNAS)
        .not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
        .or_(_sem_marca_ou_reentrada(agora)).gte("meta_created_at", settings.lead_compra_ego_desde)
        .order("meta_created_at").limit(200).execute()
    )
    return [l for l in resp.data or [] if precisa_de_lead(l, agora) and elegivel(l, agora)][:LIMITE_POR_VOLTA]


def _candidatas_interesse(agora: datetime) -> list[dict]:
    """Compradores Meta marcados com interesse real (pedido #17), **mesmo os que já responderam**. Desligado sem o segredo."""
    if not settings.lead_interesse_ego:
        return []
    resp = (
        get_supabase().table("contactos").select(_COLUNAS)
        .not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
        .not_.is_("interesse_real_em", "null").or_(_sem_marca_ou_reentrada(agora))
        .gte("meta_created_at", settings.lead_compra_ego_desde).order("interesse_real_em").limit(200).execute()
    )
    return [l for l in resp.data or [] if precisa_de_lead(l, agora) and vale_para_a_entrada(l, "interesse_real_em")][:LIMITE_POR_VOLTA]


def _conversa_do(telefone: str, desde: datetime | None = None) -> tuple[datetime | None, list[str]]:
    """Última atividade da conversa de WhatsApp deste número e o que a pessoa escreveu nela. As mensagens não têm hora:
    uma conversa cuja última atividade é anterior a `desde` (a entrada Meta) é toda da entrada anterior e não conta.
    ponytail: uma conversa que atravessa a entrada (reaproveitada em <48 h) conta inteira; separar exigia hora por mensagem."""
    resp = (
        get_supabase().table("agente_conversas").select("atualizado_em,mensagens")
        .eq("canal", "whatsapp").in_("participante", variantes_telefone(telefone))
        .order("atualizado_em", desc=True).limit(1).execute()
    )
    if not resp.data:
        return None, []
    linha = resp.data[0]
    atividade = _dt(linha.get("atualizado_em"))
    if desde and atividade and atividade < desde:
        return None, []
    textos = [m["content"] for m in linha.get("mensagens") or [] if m.get("role") == "user" and isinstance(m.get("content"), str)
              and not e_mensagem_pre_preenchida(m["content"])]
    return atividade, textos


def resumo_da_conversa(textos: list[str]) -> str:
    """As últimas 3 coisas que a pessoa escreveu, cada uma cortada. Sem a conversa inteira (vai para o OBS do eGO)."""
    return " | ".join(" ".join(t.split())[:160] for t in [t for t in textos if not e_mensagem_pre_preenchida(t)][-3:] if t.strip())[:_MAX_RESUMO_OBS]


# Os anúncios são de venda e muita gente pergunta por arrendamento (4 de 5 conversas a 03/11): o OBS diz-o à consultora.
_ARRENDAR = re.compile(r"\b(arrend\w*|alug\w*|renda)\b", re.I)
AVISO_ARRENDAR = "Atenção: falou em ARRENDAR (o imóvel do anúncio está à venda): confirmar se quer comprar ou arrendar."


def procura_arrendar(textos: list[str]) -> bool:
    return any(_ARRENDAR.search(t) for t in textos)


def _mensagens_do(telefone: str, desde: datetime | None = None) -> list[dict]:
    """Mensagens (as duas partes) da conversa de WhatsApp deste número; vazio se a conversa é anterior a `desde` (ver `_conversa_do`)."""
    resp = (
        get_supabase().table("agente_conversas").select("mensagens,atualizado_em")
        .eq("canal", "whatsapp").in_("participante", variantes_telefone(telefone))
        .order("atualizado_em", desc=True).limit(1).execute()
    )
    if not resp.data:
        return []
    atividade = _dt(resp.data[0].get("atualizado_em"))
    if desde and atividade and atividade < desde:
        return []
    return resp.data[0].get("mensagens") or []


_FRASE_PERGUNTA = re.compile(r"[^.!?\n]*\?")


def _perguntas(texto: str) -> str:
    """As perguntas (até 2) de uma mensagem da Matilde, sem markdown. Vazio se não perguntou nada."""
    perguntas = [" ".join(re.sub(r"[*_~]", "", f).split()) for f in _FRASE_PERGUNTA.findall(texto)]
    texto = " ".join(p for p in perguntas if p)
    if len(texto) > _PERGUNTA_OBS:  # fica com o fim (a pergunta em si), sem começar a meio de uma palavra
        texto = "…" + texto[-_PERGUNTA_OBS:].split(" ", 1)[-1]
    return texto


# Só cortesia («obrigada pela sua atenção, Deus te abençoe», «feliz noite», «ok»): não diz nada à consultora.
_CORTESIA = frozenset("""obrigado obrigada obrigados obrigadas muito muita muitissimo muitíssimo tambem também tabem agradecido
agradecida agradeço pela pelo sua seu atenção atencao aten deus te abençoe bencao bênção bom boa dia noite tarde feliz fim de
semana ate até logo breve ok certo""".split())


def _so_cortesia(texto: str) -> bool:
    return all(p in _CORTESIA for p in re.findall(r"\w+", texto.lower()))


def respostas_da_pessoa(mensagens: list[dict]) -> str:
    """O que a pessoa respondeu, em pares «pergunta da Matilde → resposta», para a consultora saber o que já foi apurado
    (orçamento, zona, tipologia…) sem ler a conversa. A 1.ª fala vai como «Pediu»; o que diz sem lhe terem perguntado,
    como «Disse»; agradecimentos e despedidas ficam de fora. Cabe em `_MAX_RESPOSTAS_OBS`: se não couber, caem as mais antigas.
    Vazio se a pessoa nunca escreveu. Sem IA: texto dela cortado, nada inventado."""
    itens: list[str] = []
    anterior = ""  # texto da última mensagem da Matilde
    for m in mensagens:
        texto = m.get("content")
        if m.get("role") not in ("user", "assistant") or not isinstance(texto, str) or not texto.strip():
            continue
        if m["role"] == "user" and e_mensagem_pre_preenchida(texto):
            continue  # o texto que o botão do formulário pré-preenche não é uma resposta
        if m["role"] == "assistant":
            anterior = texto
            continue
        resposta = " ".join(texto.split())[:_RESPOSTA_OBS]
        if e_fecho_da_pessoa(texto) or (itens and _so_cortesia(texto)):
            continue
        if not itens:
            itens.append(f"Pediu: {resposta}")
        elif pergunta := _perguntas(anterior):
            itens.append(f"{pergunta} → {resposta}")
        else:
            itens.append(f"Disse: {resposta}")
    if not itens:
        return ""
    primeiro, resto = itens[0], itens[1:]
    total = len(primeiro) + 5
    guardados: list[str] = []
    for item in reversed(resto):
        if total + len(item) + 3 > _MAX_RESPOSTAS_OBS:
            break
        guardados.insert(0, item)
        total += len(item) + 3
    return " | ".join([primeiro] + (["…"] if len(guardados) < len(resto) else []) + guardados)


def _com_conversa(linha: dict) -> dict:
    """Quem respondeu à Matilde: junta à linha o que respondeu às perguntas dela (vai no OBS do eGO) e o aviso de que
    falou em arrendar. Nunca levanta: sem a conversa, a lead cria-se na mesma."""
    if not (linha.get("respondeu_em") or linha.get("interesse_real_em")):
        return linha
    try:
        tel = telefone_da_linha(linha)
        mensagens = _mensagens_do(tel, _dt(linha.get("meta_created_at"))) if tel else []
    except Exception:
        logger.exception("Falha a ler a conversa da lead %s", linha.get("id"))
        return linha
    textos = [m["content"] for m in mensagens if m.get("role") == "user" and isinstance(m.get("content"), str)
              and not e_mensagem_pre_preenchida(m["content"])]
    return linha | {"procura_arrendar": procura_arrendar(textos), "respostas_da_pessoa": respostas_da_pessoa(mensagens)}


def _no_piloto(tel: str) -> bool:
    """`LEAD_RESPONDEU_EGO=1` abre a todas; uma lista («123,456») é um piloto: só os números que acabam num destes sufixos."""
    modo = settings.lead_respondeu_ego.strip()
    return modo == "1" or any(s.strip() and tel.endswith(s.strip()) for s in modo.split(","))


def _candidatas_paradas(agora: datetime) -> list[dict]:
    """Compradores Meta que **responderam** à Matilde sem nunca dar sinal de interesse (nem recusar) e deixaram a conversa
    parada há `JANELA_PARADA_HORAS`. Sem isto ficavam para sempre fora do eGO (26–27/10: 5 de 14 leads). Desligado sem o segredo."""
    if not settings.lead_respondeu_ego:
        return []
    resp = (
        get_supabase().table("contactos").select(_COLUNAS)
        .not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
        .not_.is_("respondeu_em", "null").or_(_sem_marca_ou_reentrada(agora)).is_("nao_contactar_em", "null")
        .gte("meta_created_at", settings.lead_compra_ego_desde)
        .gte("meta_created_at", (agora - timedelta(days=IDADE_MAX_PARADA_DIAS)).isoformat())
        .order("meta_created_at").limit(200).execute()
    )
    paradas = []
    for l in resp.data or []:
        if (not precisa_de_lead(l, agora) or vale_para_a_entrada(l, "contacto_humano_em") or l.get("nao_contactar_em")
                or not vale_para_a_entrada(l, "respondeu_em")):
            continue
        tel = telefone_da_linha(l)
        if not tel or not _no_piloto(tel):
            continue
        ultima, textos = _conversa_do(tel, _dt(l.get("meta_created_at")))
        if textos and (e_fecho_da_pessoa(textos[-1]) or any(e_recusa(t) for t in textos[-3:])):
            continue  # despediu-se («obrigado 🤩», «até breve») ou recusou numa das últimas 3 mensagens («do momento não tenho»)
        if ultima and ultima <= agora - timedelta(hours=JANELA_PARADA_HORAS):
            paradas.append(l | {"conversa_parada_resumo": resumo_da_conversa(textos)})
    return paradas[:LIMITE_POR_VOLTA]


def _conversa_depois(telefone: str, entrada: datetime | None, marca: datetime) -> tuple[datetime | None, list[dict]]:
    """Última atividade da conversa deste número e as mensagens **depois de `marca`** (a lead criada), as duas partes, sem a
    mensagem pré-preenchida. Só entram as que têm hora (`timestamp`): sem ela não há como saber se são posteriores."""
    resp = (
        get_supabase().table("agente_conversas").select("atualizado_em,mensagens")
        .eq("canal", "whatsapp").in_("participante", variantes_telefone(telefone))
        .order("atualizado_em", desc=True).limit(1).execute()
    )
    if not resp.data:
        return None, []
    atividade = _dt(resp.data[0].get("atualizado_em"))
    if entrada and atividade and atividade < entrada:
        return None, []
    depois = []
    for m in resp.data[0].get("mensagens") or []:
        ts = _dt(m.get("timestamp")) if isinstance(m.get("timestamp"), str) else None
        if ts and ts > marca and isinstance(m.get("content"), str) and not (m.get("role") == "user" and e_mensagem_pre_preenchida(m["content"])):
            depois.append(m)
    return atividade, depois


def _ja_tratada_depois(linha: dict) -> bool:
    """Já houve aviso «respondeu depois» desde a marca desta lead. Chave própria (não a da qualificação: o aviso imediato da
    qualificação não pode impedir a lead nova). Falha para tratada: um email a menos custa menos do que repeti-lo a cada volta."""
    titulos = titulos_da_tarefa(linha)
    if not titulos:
        return True
    try:
        r = (get_supabase().table("agente_tarefas").select("id").eq("tipo", "lead_ego_aviso").ilike("descricao", "%respondeu depois%")
             .in_("titulo", titulos).gte("criado_em", linha["ego_lead_em"]).limit(1).execute().data)
        return bool(r)
    except Exception:
        logger.exception("Falha a ver o aviso da lead %s", linha.get("id"))
        return True


def _recriada_ha_pouco(linha: dict, agora: datetime) -> bool:
    """Já se criou uma lead nova a esta pessoa nas últimas `LEAD_NOVA_MAX_POR_DIA_H` horas. Falha para sim (não cria)."""
    try:
        desde = (agora - timedelta(hours=LEAD_NOVA_MAX_POR_DIA_H)).isoformat()
        r = (get_supabase().table("agente_sync_log").select("resumo").eq("tipo", "leads_para_ego")
             .gte("executado_em", desde).limit(200).execute().data) or []
        return any((x.get("resumo") or {}).get("via") == "respondeu_depois" and str(linha["id"]) in ((x.get("resumo") or {}).get("contactos") or [])
                   for x in r)
    except Exception:
        logger.exception("Falha a ver as leads novas recentes de %s", linha.get("id"))
        return True


def _oportunidade_da_lead(linha: dict) -> str | None:
    """Ref (`VEN_…`) da oportunidade ativa desta pessoa para este imóvel, procurada na API do eGO por telefone ou email. Melhor
    esforço: sem ela, o texto diz só que a lead anterior já saiu da caixa. Nunca levanta."""
    try:
        tel = (telefone_da_linha(linha) or "")[-9:]
        email = (linha.get("email") or "").strip().lower()
        for o in ego_api.oportunidades_ativas():
            if linha.get("imovel_ref") and _ref_base(o.get("realestateReference")) != _ref_base(linha["imovel_ref"]):
                continue
            if (tel and tel in "".join(c for c in (o.get("phone") or "") if c.isdigit())) or (email and (o.get("email") or "").strip().lower() == email):
                return o.get("name")
    except Exception:
        logger.exception("Falha a procurar a oportunidade da lead %s", linha.get("id"))
    return None


def _candidatas_respondeu_depois(agora: datetime) -> list[dict]:
    """Compradores Meta cuja lead **já está no eGO** (marca desta entrada) e que escreveram à Matilde **depois** dela, com a
    conversa assente (`JANELA_PARADA_HORAS`) e sem recusa nem despedida. Cada candidata traz `_depois` (as mensagens depois da
    marca) e `_ultima` (última atividade). Desligado sem `LEAD_RESPONDEU_EGO` (mesmo interruptor/piloto da porta «conversa parada»)."""
    if not settings.lead_respondeu_ego:
        return []
    resp = (
        get_supabase().table("contactos").select(_COLUNAS + ",ego_lead_id")
        .not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
        .not_.is_("ego_lead_em", "null").not_.is_("ego_lead_id", "null").not_.is_("respondeu_em", "null").is_("nao_contactar_em", "null")
        .gte("meta_created_at", settings.lead_compra_ego_desde)
        .gte("meta_created_at", (agora - timedelta(days=IDADE_MAX_PARADA_DIAS)).isoformat())
        .order("meta_created_at").limit(200).execute()
    )  # `ego_lead_id`: só leads nossas; uma marca de «já existia» (oportunidade ativa) não tem id e não é lead a recriar
    candidatas = []
    for l in resp.data or []:
        if not vale_para_a_entrada(l, "ego_lead_em"):
            continue
        tel = telefone_da_linha(l)
        if not tel or not _no_piloto(tel):
            continue
        ultima, depois = _conversa_depois(tel, _dt(l.get("meta_created_at")), _dt(l["ego_lead_em"]))
        if not depois or not ultima or ultima > agora - timedelta(hours=JANELA_PARADA_HORAS):
            continue  # nada de novo, ou ainda a conversar: espera-se que assente para tratar uma vez com o resumo completo
        textos = [m["content"] for m in depois if m.get("role") == "user"]
        if not textos or e_fecho_da_pessoa(textos[-1]) or any(e_recusa(t) or e_fora_do_alcance(t) for t in textos[-3:]):
            continue
        if not l.get("ego_lead_id"):
            continue
        if not _ja_tratada_depois(l):
            candidatas.append(l | {"_depois": depois, "_ultima": ultima})
    return candidatas[:LIMITE_POR_VOLTA]


def _registar_aviso(linha: dict, descricao: str) -> None:
    get_supabase().table("agente_tarefas").insert({
        "titulo": f"{_TAREFA_QUALIFICADA} — {linha.get('nome') or telefone_da_linha(linha)}",
        "tipo": "lead_ego_aviso", "estado": "concluida", "agente": "a1_vendedor", "descricao": descricao,
    }).execute()


def _email_respondeu_depois(linha: dict, situacao: str) -> None:
    resumo = respostas_da_pessoa(linha["_depois"])
    corpo = "\n".join(p for p in (
        f"{linha.get('nome') or 'Uma pessoa'} (lead da Meta, imóvel {linha.get('imovel_ref') or '—'}) voltou a escrever à Matilde.",
        situacao, "",
        f"Telefone: {telefone_da_linha(linha) or '—'} · Email: {linha.get('email') or '—'}",
        f"Respostas da pessoa: {resumo}" if resumo else None,
        AVISO_ARRENDAR if procura_arrendar([m["content"] for m in linha["_depois"] if m.get("role") == "user"]) else None,
    ) if p is not None)
    notificar(f"Lead já no eGO voltou a responder — {linha.get('imovel_ref') or 'imóvel?'}", corpo, imovel_ref=linha.get("imovel_ref"))


def tratar_respondeu_depois(agora: datetime) -> dict:
    """A lead que criámos já tem conversa nova. Se a lead **continua na caixa**, email à consultora. Se **já não existe ou já foi
    convertida**, cria-se uma lead nova (regra do utilizador, 23/11), no máximo uma por pessoa e por dia, e só com
    `LEAD_NOVA_DEPOIS_DESDE` preenchido e conversa posterior a essa data (sem ele só há email). Nunca levanta.
    Devolve `{"avisadas": n, "criadas": n, "erros": n}`."""
    contagem = {"avisadas": 0, "criadas": 0, "erros": 0}
    try:
        candidatas = _candidatas_respondeu_depois(agora)
        if not candidatas:
            return contagem
        leads = ego_api.leads_abertas()  # sem saber o que lá está não se decide nada nesta volta
    except Exception:
        logger.exception("Falha a procurar leads que responderam depois de criadas")
        return contagem | {"erros": 1}
    ativacao = _dt(settings.lead_nova_depois_desde) if settings.lead_nova_depois_desde else None
    for l in candidatas:
        try:
            l = _imovel_da_entrada(l)
            ids = {str(x.get("id")) for x in leads}
            na_caixa = str(l.get("ego_lead_id")) in ids or _lead_da_caixa(l, leads) is not None
            if na_caixa:
                _registar_aviso(l, "Lead já no eGO respondeu depois de criada; consultora avisada por email.")
                _email_respondeu_depois(l, "A lead continua na caixa de leads do eGO, com o texto de quando foi criada (sem esta conversa): "
                                           "acrescenta uma nota com o que ela disse.")
                contagem["avisadas"] += 1
                continue
            novas = [m for m in l["_depois"] if ativacao and (_dt(m["timestamp"]) or ativacao) > ativacao]
            if not ativacao or not novas or _recriada_ha_pouco(l, agora):
                continue  # sem licença para criar, conversa anterior à ativação, ou já se criou uma hoje: nada
            if not (l.get("email") or "").strip():
                logger.warning("Lead %s sem email: não se cria lead nova no eGO (Web API exige)", l["id"])
                contagem["erros"] += 1
                continue
            oportunidade = _oportunidade_da_lead(l)
            nova = l | {"voltou_a_responder": True, "oportunidade_anterior": oportunidade,
                        "respostas_da_pessoa": respostas_da_pessoa(l["_depois"]),
                        "procura_arrendar": procura_arrendar([m["content"] for m in l["_depois"] if m.get("role") == "user"])}
            tel = telefone_da_linha(nova)
            ident = _criar_lead(nova, tel, ja_conhecido=True) or _id_da_lead(tel, nova.get("email"))
            marca = {"ego_lead_em": agora.isoformat()} | ({"ego_lead_id": ident} if ident else {})
            get_supabase().table("contactos").update(marca).eq("id", l["id"]).execute()
            registar_marcas("respondeu_depois", agora, [l["id"]], criadas=1, oportunidade=oportunidade)
            fechar_tarefas_da_lead(l)
            _email_respondeu_depois(l, "A lead anterior já estava em tratamento"
                                       + (f" (oportunidade {oportunidade})" if oportunidade else " (já fora da caixa de leads)")
                                       + ": criou-se uma lead nova no eGO com esta conversa.")
            contagem["criadas"] += 1
        except SemConsultora as e:
            logger.warning("Lead %s não criada: %s", l["id"], e)
            contagem["erros"] += 1
        except Exception:
            logger.exception("Falha a tratar a lead %s que respondeu depois", l.get("id"))
            contagem["erros"] += 1
    return contagem


def angariador_da_ref(ref: str | None, por_ref: dict[str, str]) -> str | None:
    """Angariador do imóvel pela ref exata ou, se vier com sufixo («FH2584_V1»), pela curta («FH2584»)."""
    if not ref:
        return None
    curta = (re.match(r"[A-Za-z]*\d+", ref) or [None])[0]
    return por_ref.get(ref) or (por_ref.get(curta.upper()) if curta else None)


def preencher_responsavel_meta() -> dict:
    """Rede do pedido #17 (plano `responsavel-leads-meta-plano.md`): o RPC `lead_meta_compra` grava o angariador à entrada; se o imóvel
    só chegou a `imoveis` depois, aqui preenche-se o que ficou vazio (`leads` sempre, `contactos` só vazios, compradores Meta).
    Nunca levanta nem sobrescreve."""
    feitas = {"leads": 0, "contactos": 0}
    try:
        sb = get_supabase()
        vazio = "responsavel.is.null,responsavel.eq."
        leads = sb.table("leads").select("id,meta_lead_id,imovel_ref").not_.is_("meta_lead_id", "null").not_.is_("imovel_ref", "null").or_(vazio).limit(200).execute().data or []
        contactos = (sb.table("contactos").select("id,meta_lead_id,imovel_ref").not_.is_("meta_lead_id", "null").contains("tipo_contacto", ["comprador"])
                     .or_(vazio).limit(200).execute().data or [])
        ref_da_lead = {l["meta_lead_id"]: l["imovel_ref"] for l in leads}
        falta = [c["meta_lead_id"] for c in contactos if c["meta_lead_id"] not in ref_da_lead]
        for i in range(0, len(falta), 100):
            for l in sb.table("leads").select("meta_lead_id,imovel_ref").in_("meta_lead_id", falta[i:i + 100]).execute().data or []:
                ref_da_lead[l["meta_lead_id"]] = l["imovel_ref"]
        for c in contactos:  # contacto sem linha em `leads` (formulários, importações): vale o `imovel_ref` dele
            if not ref_da_lead.get(c["meta_lead_id"]) and c.get("imovel_ref"):
                ref_da_lead[c["meta_lead_id"]] = c["imovel_ref"]
        refs = {r for r in ref_da_lead.values() if r}
        refs |= {(re.match(r"[A-Za-z]*\d+", r) or [""])[0].upper() for r in refs}
        por_ref: dict[str, str] = {}
        lista = sorted(r for r in refs if r)
        for i in range(0, len(lista), 100):
            for im in sb.table("imoveis").select("imovel_ref,angariador").in_("imovel_ref", lista[i:i + 100]).execute().data or []:
                if (im.get("angariador") or "").strip():
                    por_ref[im["imovel_ref"]] = im["angariador"]
        for l in leads:
            if nome := angariador_da_ref(l["imovel_ref"], por_ref):
                sb.table("leads").update({"responsavel": nome}).eq("id", l["id"]).execute()
                feitas["leads"] += 1
        for c in contactos:
            if nome := angariador_da_ref(ref_da_lead.get(c["meta_lead_id"]), por_ref):
                sb.table("contactos").update({"responsavel": nome}).eq("id", c["id"]).or_(vazio).execute()
                feitas["contactos"] += 1
    except Exception:
        logger.exception("Falha a preencher o responsável das leads Meta")
    return feitas


def titulos_da_tarefa(linha: dict) -> list[str]:
    """Títulos que `guards._promover_lead` pode ter dado à tarefa «passar ao eGO» desta pessoa (nome, telefone ou email)."""
    quem = {linha.get("nome"), linha.get("email")}
    for campo in ("telefone", "telemovel"):
        tel = normalizar_telefone(linha.get(campo))
        quem |= {linha.get(campo), *(variantes_telefone(tel) if tel else ())}
    return [f"{_TAREFA_QUALIFICADA} — {q}" for q in quem if q]


def fechar_tarefas_da_lead(linha: dict) -> None:
    """A lead já está no eGO: a tarefa «passar ao eGO» (`tipo='lead_ego'`) deixa de fazer sentido. Nunca levanta.

    Chave = título. ponytail: duas pessoas com o mesmo nome e sem telefone partilham o fecho; se acontecer,
    `contacto_id` em `agente_tarefas`."""
    titulos = titulos_da_tarefa(linha)
    if not titulos:
        return
    try:
        (get_supabase().table("agente_tarefas")
         .update({"estado": "concluida", "atualizado_em": datetime.now(timezone.utc).isoformat()})
         .eq("tipo", "lead_ego").eq("estado", "pendente").in_("titulo", titulos).execute())
    except Exception:
        logger.exception("Falha a fechar a tarefa da lead %s", linha.get("id"))


def processar(agora: datetime | None = None) -> dict:
    """Uma volta do cron. Falha da API deixa a lead por marcar (a próxima volta repete)."""
    if not settings.lead_compra_ego_desde:
        return {"ativo": False}
    agora = agora or datetime.now(timezone.utc)
    preencher_responsavel_meta()
    contagem = {"ativo": True, "criadas": 0, "ja_existiam": 0, "erros": 0}
    depois = tratar_respondeu_depois(agora)
    if depois["avisadas"] or depois["criadas"] or depois["erros"]:
        contagem["respondeu_depois"] = depois
    candidatas = _candidatas(agora)
    vistas = {l["id"] for l in candidatas}
    candidatas += [l for l in _candidatas_interesse(agora) if l["id"] not in vistas]
    vistas = {l["id"] for l in candidatas}
    candidatas += [l for l in _candidatas_paradas(agora) if l["id"] not in vistas]
    if not candidatas:
        return contagem
    candidatas = [_com_conversa(_imovel_da_entrada(l)) for l in candidatas]
    try:
        leads = ego_api.leads_abertas()  # sem saber o que lá está, criar podia duplicar: nesta volta não se cria
    except Exception:
        logger.exception("Falha a ler as leads do eGO — nenhuma lead criada nesta volta")
        return contagem | {"erros": len(candidatas)}
    marcadas = []
    for linha in candidatas:
        marca = {"ego_lead_em": agora.isoformat()}
        try:
            tel = telefone_da_linha(linha)
            na_caixa = _lead_da_caixa(linha, leads)
            ops = [] if na_caixa else _oportunidades_ativas(tel, linha.get("email"))
            if na_caixa:
                contagem["ja_existiam"] += 1
                if str(na_caixa.get("id", "")).isdigit():
                    marca["ego_lead_id"] = int(na_caixa["id"])  # pedido #17(d): a marca leva o id sempre que o eGO o dá
                _avisar_lead_na_caixa(linha, na_caixa)
            elif ops and _mesmo_imovel(ops, linha.get("imovel_ref")):
                contagem["ja_existiam"] += 1
                contagem["avisadas"] = contagem.get("avisadas", 0) + 1
                _avisar_oportunidade_ativa(linha, ops)
            elif not (linha.get("email") or "").strip():  # a Web API recusa sem email: fica por criar, à vista
                logger.warning("Lead %s sem email: não se cria no eGO (Web API exige)", linha["id"])
                contagem["erros"] += 1
                continue
            else:
                # oportunidade ativa de OUTRO imóvel (pedido #17, 10/11): é interesse novo, cria-se a lead deste imóvel
                ident = _criar_lead(linha, tel, ja_conhecido=bool(ops) or _ja_nas_leads(linha, leads)) or _id_da_lead(tel, linha.get("email"))  # a Web API não devolve o id
                if ident:
                    marca["ego_lead_id"] = ident
                contagem["criadas"] += 1
            get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
            marcadas.append(linha["id"])
            fechar_tarefas_da_lead(linha)
        except SemConsultora as e:
            logger.warning("Lead %s não criada: %s", linha["id"], e)
            contagem["erros"] += 1
        except Exception:
            logger.exception("Falha a enviar a lead %s para o eGO", linha["id"])
            contagem["erros"] += 1
    if marcadas:
        registar_marcas("cron", agora, marcadas, criadas=contagem["criadas"], ja_existiam=contagem["ja_existiam"],
                        avisadas=contagem.get("avisadas", 0))
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
    linha = _ler_entrada(meta_lead_id)
    if linha is None:
        return None
    if parar := _travao_da_entrada(linha):
        return parar
    # o RPC da compra não grava `imovel_ref` em `contactos` para quem recusa: vem do n8n, ou do nome do anúncio
    linha["imovel_ref"] = linha.get("imovel_ref") or (imovel_ref or "").strip() or ref_do_anuncio(linha.get("ad_name"))
    return _criar_pela_entrada(linha, datetime.now(timezone.utc), recusou=True, via="recusa")


def _ler_entrada(meta_lead_id: str) -> dict | None:
    linhas = (get_supabase().table("contactos").select(_COLUNAS)
              .eq("meta_lead_id", meta_lead_id).limit(1).execute().data)
    return linhas[0] if linhas else None


def _travao_da_entrada(linha: dict) -> dict | None:
    """Resposta de quem não deve criar nada: já tratada, ou entrada anterior à ativação. `None` = pode seguir."""
    if vale_para_a_entrada(linha, "ego_lead_em"):  # uma marca de entrada anterior não trata esta entrada
        return {"resultado": "ja_tratada"}
    # compara-se por dia (a data de ativação é um dia) e pela entrada da lead Meta, não pelo `criado_em` do contacto
    if entrou_pela_meta_em(linha) < str(settings.lead_compra_ego_desde)[:10]:
        return {"resultado": "anterior_a_ativacao", "criada": False}
    return None


def _criar_pela_entrada(linha: dict, agora: datetime, *, recusou: bool, via: str, gravar_imovel: bool = True) -> dict:
    """Parte comum da recusa e da entrada: confirma a caixa e as oportunidades ativas, cria a lead, marca, devolve o resultado.
    Falha do PUT levanta (nada marcado); `gravar_imovel` falso deixa o `imovel_ref` do contacto como está."""
    tel = telefone_da_linha(linha)
    email = linha.get("email")
    try:
        leads = ego_api.leads_abertas()
        na_caixa = bool(_lead_da_caixa(linha, leads))
        verificado = True
    except Exception:
        logger.exception("Falha a ler as leads do eGO — a criar sem confirmar")
        na_caixa, verificado = False, False

    responsavel = _responsavel_do_mesmo_imovel(tel, email, linha.get("imovel_ref"))
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
            id_lead = _criar_lead(linha, tel, recusou=recusou, ja_conhecido=_contacto_conhecido(linha, tel))
        except SemConsultora as e:  # não marca: o email diz para criar à mão
            logger.warning("Entrada %s (%s): lead não criada (%s)", linha["id"], via, e)
            return {"resultado": "sem_consultora", "criada": False, "verificado_no_ego": verificado,
                    "responsavel": None, "email_responsavel": None}
        if not id_lead and verificado:  # a Web API não devolve o id: apanha-se na caixa do eGO (melhor esforço)
            id_lead = _id_da_lead(tel, email)
        if id_lead:
            marca["ego_lead_id"] = id_lead
    if linha.get("imovel_ref") and gravar_imovel:
        marca["imovel_ref"] = linha["imovel_ref"]  # fica para os follow-ups e para quem ler o contacto
    get_supabase().table("contactos").update(marca).eq("id", linha["id"]).execute()
    fechar_tarefas_da_lead(linha)
    registar_marcas(via, agora, [linha["id"]], resultado=resultado)
    return {"resultado": resultado, "criada": resultado == "criada", "verificado_no_ego": verificado,
            "responsavel": responsavel, "email_responsavel": _email_do_responsavel(responsavel)}


def aceitou_whatsapp(resposta: str | None) -> bool:
    """A resposta crua do formulário começa por «sim»: a regra do `Guardas` do n8n. Nunca `whatsapp_permissao`, que o RPC pode
    calcular de forma laxa (o de angariação marcava True a quem recusava). Sem resposta conta como recusa."""
    return (resposta or "").strip().lower().startswith("sim")


def _reservar(linha: dict, agora: datetime) -> bool:
    """Reserva a criação: `ego_lead_em` só passa do valor que lemos para `agora` uma vez. Quem perde (webhook repetido da Meta,
    n8n em repetição) não chega ao eGO e não cria uma 2.ª lead."""
    q = get_supabase().table("contactos").update({"ego_lead_em": agora.isoformat()}).eq("id", linha["id"])
    q = q.eq("ego_lead_em", linha["ego_lead_em"]) if linha.get("ego_lead_em") else q.is_("ego_lead_em", "null")
    return bool(q.execute().data)


def _libertar(linha: dict) -> None:
    """Repõe a marca que a linha tinha antes da reserva (a lead não ficou criada: o cron apanha-a 2 h depois)."""
    get_supabase().table("contactos").update({"ego_lead_em": linha.get("ego_lead_em")}).eq("id", linha["id"]).execute()


def entrada_meta(meta_lead_id: str, imovel_ref: str | None = None, whatsapp_optin: str | None = None) -> dict | None:
    """Lead de compra que acabou de entrar no Supabase: cria-a no eGO já, sem esperar a conversa (pedido #17, chamado pelo n8n logo
    a seguir ao RPC). Mesmos casos de `recusou_whatsapp`, mais a reserva antes de chamar o eGO.

    Único ponto de criação, para quem aceita e para quem recusa o WhatsApp (a recusa leva o OBS «contactar por telefone» e a
    marca `via=recusa`; `recusou_whatsapp` fica só como reversão). Desligado com `LEAD_ENTRADA_EGO` ou `LEAD_COMPRA_EGO_DESDE` vazios. `None` = contacto inexistente. Não cria sem email nem sem
    consultora: nesses casos liberta a reserva e diz porquê (o endpoint responde 502 para o n8n avisar). Falha do eGO levanta."""
    if not (settings.lead_compra_ego_desde and settings.lead_entrada_ego):
        return {"resultado": "desligado", "criada": False}
    recusou = not aceitou_whatsapp(whatsapp_optin)
    linha = _ler_entrada(meta_lead_id)
    if linha is None:
        return None
    if parar := _travao_da_entrada(linha):
        return parar
    tinha_imovel = linha.get("imovel_ref")  # numa reentrada é o da 1.ª entrada: o do n8n manda e o do contacto fica como está
    linha["imovel_ref"] = (imovel_ref or "").strip() or tinha_imovel or ref_do_anuncio(linha.get("ad_name"))
    linha["acabou_de_entrar"] = not recusou  # quem recusou leva o OBS da recusa
    agora = datetime.now(timezone.utc)
    if not _reservar(linha, agora):
        return {"resultado": "ja_tratada"}
    try:
        r = _criar_pela_entrada(linha, agora, recusou=recusou, via="recusa" if recusou else "entrada",
                                gravar_imovel=not tinha_imovel)
    except Exception:
        _libertar(linha)
        raise
    if r["resultado"] in ("sem_email", "sem_consultora"):
        _libertar(linha)
    return r
