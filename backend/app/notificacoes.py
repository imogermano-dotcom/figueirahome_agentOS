"""Aviso ao corretor quando acontece algo que não pode esperar pelo painel.

Antes disto, uma lead qualificada e um escalamento acabavam ambos numa linha em
`agente_tarefas` e mais nada — se ninguém abrisse o painel, a lead paga que
qualificou às 23h ficava lá até alguém reparar. Uma lead imobiliária é
perecível; a tarefa continua a ser o registo, isto é o toque no ombro.

**Resend, não Microsoft Graph** (revisto 2026-08-31 — ver docs/decisoes.md). O
Graph chegou a ser configurado mas nunca teve credenciais em produção; Resend
é mais simples (API key estática, sem OAuth) para o mesmo caso de uso.

Duas decisões que se mantêm de antes:

* **Uma só função pública.** Trocar de canal — já aconteceu uma vez — mexe
  aqui e em mais lado nenhum. Os dois sítios que notificam não sabem do canal.
* **Síncrona e nunca levanta.** Ambos os chamadores já correm dentro de
  executores; falhar a enviar um aviso não pode derrubar uma conversa nem
  impedir a tarefa de ser criada — a tarefa é a rede de segurança do email.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # o envio não pode prender o turno; falhar depressa e seguir


def destinatarios() -> list[str]:
    """Quem recebe sempre — o director comercial. A consultora do imóvel entra
    por cima, resolvida a cada aviso (`_consultor_do_imovel`)."""
    return [e.strip() for e in settings.notificacoes_para.split(",") if e.strip()]


def _consultor_do_imovel(imovel_ref: str) -> tuple[str | None, str]:
    """Email de quem angariou o imóvel, e o motivo quando não há.

    Duas consultas em **bases diferentes**, por isso não há join: `imoveis` vive
    no projecto de dados e `profiles` no de autenticação. A ponte é
    `profiles.ego_responsavel`, que guarda o nome tal como o eGO o escreve.

    A cobertura é parcial e **não é uma tarefa de configuração por fazer**: a
    2026-08-16, 21 dos 54 imóveis publicados (39%) estavam atribuídos a pessoas
    que já saíram da agência — Lina Galvão (14), Ana Daniel (5), Maria José Boia
    (2). Criar-lhes perfil seria errado; o que falta é reatribuir a carteira no
    eGO, e isso é trabalho de backoffice, não nosso.

    Por isso o motivo devolvido é **neutro**. Uma mensagem a mandar "preencher o
    `profiles`" levaria alguém, daqui a uns meses, a criar contas a
    ex-colaboradoras a partir de um email automático.
    """
    from app.db.supabase_client import get_supabase, get_supabase_auth

    try:
        im = (
            get_supabase().table("imoveis").select("angariador")
            .eq("imovel_ref", imovel_ref).limit(1).execute().data
        )
        if not im:
            return None, f"imóvel {imovel_ref} não existe na base"
        nome = (im[0].get("angariador") or "").strip()
        if not nome:
            return None, f"o imóvel {imovel_ref} não tem angariador no eGO"

        perfil = (
            get_supabase_auth().table("profiles").select("email")
            .eq("ego_responsavel", nome).limit(1).execute().data
        )
        if not perfil or not perfil[0].get("email"):
            return None, (
                f"o imóvel {imovel_ref} está atribuído a {nome}, que não tem "
                "consultora activa associada — reatribuir no eGO"
            )
        return perfil[0]["email"], nome
    except Exception:
        logger.exception("Falha a resolver o consultor de %s", imovel_ref)
        return None, "erro a resolver o consultor (ver logs)"


def configurado() -> bool:
    """Sem API key ou sem destinatário, as notificações estão desligadas.

    Estado normal e não erro: permite ter isto em produção antes de existirem
    credenciais, e ligar sem novo deploy.
    """
    return bool(settings.resend_api_key and settings.resend_remetente and destinatarios())


def notificar(assunto: str, corpo: str, imovel_ref: str | None = None) -> None:
    """Manda o aviso. Engole tudo o que corra mal — ver docstring do módulo.

    Com `imovel_ref`, acrescenta a consultora que angariou esse imóvel aos
    destinatários. Sem ele, ou sem mapeamento, vai só ao director comercial — e
    o corpo diz porquê, para se ver que falta um dado em vez de parecer que o
    sistema ignorou alguém.
    """
    if not configurado():
        logger.debug("Notificações desligadas (sem API key do Resend ou destinatário).")
        return

    para = list(destinatarios())
    if imovel_ref:
        email, motivo = _consultor_do_imovel(imovel_ref)
        if email:
            corpo += f"\n\nConsultor do imóvel {imovel_ref}: {motivo} <{email}>"
            if email not in para:  # o director pode ser o angariador
                para.append(email)
        else:
            corpo += f"\n\nSem consultor atribuído — {motivo}."

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_remetente,
                "to": para,
                "subject": assunto,
                "text": corpo,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Notificação enviada: %s", assunto)
    except httpx.HTTPStatusError as e:
        # O corpo do Resend diz o que falhou (domínio não verificado, remetente
        # inválido); sem ele o diagnóstico é adivinhar.
        logger.error(
            "Falha ao notificar (%s): HTTP %s — %s",
            assunto, e.response.status_code, e.response.text[:300],
        )
    except Exception:
        logger.exception("Falha ao notificar (%s) — a tarefa fica na mesma.", assunto)


def demo() -> None:
    """Auto-verificação das guardas. `python -m app.notificacoes` de `backend/`"""
    original = (settings.resend_api_key, settings.resend_remetente, settings.notificacoes_para)
    try:
        settings.resend_api_key = settings.resend_remetente = ""
        settings.notificacoes_para = ""
        assert configurado() is False
        notificar("x", "y")  # não pode levantar nem gerar tráfego

        settings.resend_api_key = "k"
        settings.resend_remetente = "avisos@exemplo.pt"
        assert configurado() is False, "sem destinatário continua desligado"

        settings.notificacoes_para = " a@b.pt ,, c@d.pt "
        assert destinatarios() == ["a@b.pt", "c@d.pt"], destinatarios()
        assert configurado() is True

        # Sem rede/chave real: tem de falhar em silêncio, não rebentar.
        notificar("teste", "corpo")
    finally:
        settings.resend_api_key, settings.resend_remetente, settings.notificacoes_para = original

    print("notificacoes OK")


if __name__ == "__main__":
    demo()
