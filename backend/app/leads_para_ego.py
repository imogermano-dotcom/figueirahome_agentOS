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

from app.agents.broker.guards import _TAREFA_QUALIFICADA, e_fecho_da_pessoa, e_recusa, normalizar_telefone, variantes_telefone
from app.config import settings
from app.db.supabase_client import get_supabase
from app.integrations import ego_api, egorealestate

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
JANELA_PARADA_HORAS = 4  # conversa sem mensagens (nem o lembrete) há este tempo: a pessoa já não vai responder

_COLUNAS = ("id,nome,telefone,telemovel,email,meta_lead_id,imovel_ref,ad_name,meta_form_name,criado_em,"
            "meta_created_at,template_enviado_em,respondeu_em,contacto_humano_em,whatsapp_falhou_em,"
            "interesse_real_em,interesse_real_motivo,interesse_real_resumo,nao_contactar_em")


def dentro_do_horario(agora: datetime) -> bool:
    """Das 9h às 20h, hora de Lisboa. Só o nudge o respeita; a criação de leads no eGO já não."""
    return HORA_ABRE <= agora.astimezone(ZoneInfo("Europe/Lisbon")).hour < HORA_FECHA


def registar_marcas(via: str, agora: datetime, ids: list, **extra) -> None:
    """Deixa em `agente_sync_log` a hora (UTC e de Lisboa) a que se marcaram leads: a 04/11 apareceram 8 criações às 07:20 UTC,
    fora das 9h–20h, e os logs do Fly já não chegavam lá. Nunca levanta."""
    try:
        resumo = {"via": via, "agora_utc": agora.isoformat(), "hora_lisboa": agora.astimezone(ZoneInfo("Europe/Lisbon")).isoformat(),
                  "dentro_do_horario": dentro_do_horario(agora), "contactos": [str(i) for i in ids], **extra}
        get_supabase().table("agente_sync_log").insert({"tipo": "leads_para_ego", "resumo": resumo, "origem": "cron" if via == "cron" else "n8n"}).execute()
    except Exception:
        logger.exception("Falha a registar as marcas de leads_para_ego")


def entrou_pela_meta_em(linha: dict) -> str:
    """Dia (AAAA-MM-DD) em que a lead Meta entrou. É `meta_created_at`, não `contactos.criado_em`: quando a pessoa já existia no
    eGO (contacto antigo), a lead Meta reaproveita a linha e o `criado_em` fica na data original, o que a excluía de tudo
    (26/10: um comprador de 14/08 escalado com interesse real nunca era apanhado). `criado_em` só como último recurso."""
    return str(linha.get("meta_created_at") or linha.get("criado_em") or "")[:10]


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


def elegivel(linha: dict, agora: datetime) -> bool:
    """Sem resposta e sem consultor, e (número sem WhatsApp, ou template enviado há mais de 2 h). Nunca a quem recusou."""
    if linha.get("respondeu_em") or linha.get("contacto_humano_em") or linha.get("ego_lead_em") or linha.get("nao_contactar_em"):
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
    elif "conversa_parada_resumo" in linha:  # respondeu à Matilde, mas a conversa parou sem sinal de interesse
        resumo = linha["conversa_parada_resumo"]
        obs = [f"Lead Meta Ads (anúncio {linha['ad_name']})" if linha.get("ad_name") else "Lead Meta Ads",
               "respondeu à Matilde mas a conversa parou sem pedido de visita.",
               f"Disse: {resumo}" if resumo else "", "Contactar por telefone ou WhatsApp."]
        obs = [o for o in obs if o]
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
        .not_.is_("interesse_real_em", "null").is_("ego_lead_em", "null").is_("nao_contactar_em", "null")
        .gte("meta_created_at", settings.lead_compra_ego_desde).order("interesse_real_em").limit(LIMITE_POR_VOLTA).execute()
    )
    return [l for l in resp.data or [] if not l.get("ego_lead_em") and not l.get("nao_contactar_em")]


def _conversa_do(telefone: str) -> tuple[datetime | None, list[str]]:
    """Última atividade da conversa de WhatsApp deste número e o que a pessoa escreveu nela."""
    resp = (
        get_supabase().table("agente_conversas").select("atualizado_em,mensagens")
        .eq("canal", "whatsapp").in_("participante", variantes_telefone(telefone))
        .order("atualizado_em", desc=True).limit(1).execute()
    )
    if not resp.data:
        return None, []
    linha = resp.data[0]
    textos = [m["content"] for m in linha.get("mensagens") or [] if m.get("role") == "user" and isinstance(m.get("content"), str)]
    return _dt(linha.get("atualizado_em")), textos


def resumo_da_conversa(textos: list[str]) -> str:
    """As últimas 3 coisas que a pessoa escreveu, cada uma cortada. Sem a conversa inteira (vai para o OBS do eGO)."""
    return " | ".join(" ".join(t.split())[:160] for t in textos[-3:] if t.strip())[:_MAX_RESUMO_OBS]


# Os anúncios são de venda e muita gente pergunta por arrendamento (4 de 5 conversas a 03/11): o OBS diz-o à consultora.
_ARRENDAR = re.compile(r"\b(arrend\w*|alug\w*|renda)\b", re.I)
AVISO_ARRENDAR = "Atenção: falou em ARRENDAR (o imóvel do anúncio está à venda): confirmar se quer comprar ou arrendar."


def procura_arrendar(textos: list[str]) -> bool:
    return any(_ARRENDAR.search(t) for t in textos)


def _mensagens_do(telefone: str) -> list[dict]:
    """Mensagens (as duas partes) da conversa de WhatsApp deste número."""
    resp = (
        get_supabase().table("agente_conversas").select("mensagens")
        .eq("canal", "whatsapp").in_("participante", variantes_telefone(telefone))
        .order("atualizado_em", desc=True).limit(1).execute()
    )
    return (resp.data[0].get("mensagens") if resp.data else None) or []


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
        tel = normalizar_telefone(linha.get("telefone") or linha.get("telemovel"))
        mensagens = _mensagens_do(tel) if tel else []
    except Exception:
        logger.exception("Falha a ler a conversa da lead %s", linha.get("id"))
        return linha
    textos = [m["content"] for m in mensagens if m.get("role") == "user" and isinstance(m.get("content"), str)]
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
        .not_.is_("respondeu_em", "null").is_("ego_lead_em", "null").is_("contacto_humano_em", "null").is_("nao_contactar_em", "null")
        .gte("meta_created_at", settings.lead_compra_ego_desde)
        .gte("meta_created_at", (agora - timedelta(days=IDADE_MAX_PARADA_DIAS)).isoformat())
        .order("meta_created_at").limit(200).execute()
    )
    paradas = []
    for l in resp.data or []:
        if l.get("ego_lead_em") or l.get("contacto_humano_em") or l.get("nao_contactar_em") or not l.get("respondeu_em"):
            continue
        tel = normalizar_telefone(l.get("telefone") or l.get("telemovel"))
        if not tel or not _no_piloto(tel):
            continue
        ultima, textos = _conversa_do(tel)
        if textos and (e_fecho_da_pessoa(textos[-1]) or any(e_recusa(t) for t in textos[-3:])):
            continue  # despediu-se («obrigado 🤩», «até breve») ou recusou numa das últimas 3 mensagens («do momento não tenho»)
        if ultima and ultima <= agora - timedelta(hours=JANELA_PARADA_HORAS):
            paradas.append(l | {"conversa_parada_resumo": resumo_da_conversa(textos)})
    return paradas[:LIMITE_POR_VOLTA]


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
    candidatas = _candidatas(agora)
    vistas = {l["id"] for l in candidatas}
    candidatas += [l for l in _candidatas_interesse() if l["id"] not in vistas]
    vistas = {l["id"] for l in candidatas}
    candidatas += [l for l in _candidatas_paradas(agora) if l["id"] not in vistas]
    if not candidatas:
        return contagem
    candidatas = [_com_conversa(l) for l in candidatas]
    try:
        leads = ego_api.leads_abertas()  # sem saber o que lá está, criar podia duplicar: nesta volta não se cria
    except Exception:
        logger.exception("Falha a ler as leads do eGO — nenhuma lead criada nesta volta")
        return contagem | {"erros": len(candidatas)}
    marcadas = []
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
            marcadas.append(linha["id"])
            fechar_tarefas_da_lead(linha)
        except SemConsultora as e:
            logger.warning("Lead %s não criada: %s", linha["id"], e)
            contagem["erros"] += 1
        except Exception:
            logger.exception("Falha a enviar a lead %s para o eGO", linha["id"])
            contagem["erros"] += 1
    if marcadas:
        registar_marcas("cron", agora, marcadas, criadas=contagem["criadas"], ja_existiam=contagem["ja_existiam"])
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
    fechar_tarefas_da_lead(linha)
    registar_marcas("recusa", agora, [linha["id"]], resultado=resultado)
    return {"resultado": resultado, "criada": resultado == "criada", "verificado_no_ego": verificado,
            "responsavel": responsavel, "email_responsavel": _email_do_responsavel(responsavel)}
