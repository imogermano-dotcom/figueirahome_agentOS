"""Aviso ao corretor quando acontece algo que não pode esperar pelo painel.

Antes disto, uma lead qualificada e um escalamento acabavam ambos numa linha em
`agente_tarefas` e mais nada — se ninguém abrisse o painel, a lead paga que
qualificou às 23h ficava lá até alguém reparar. Uma lead imobiliária é
perecível; a tarefa continua a ser o registo, isto é o toque no ombro.

Três decisões deliberadas:

* **`smtplib` da biblioteca padrão**, não um serviço transaccional. Zero
  dependências novas e zero contas para gerir. Resend/SendGrid entregam melhor
  (SPF/DKIM, retentativas); se a entrega vier a ser problema, troca-se o corpo
  de `_enviar` e mais nada — é por isso que só há uma função pública.
* **Síncrona.** `smtplib` bloqueia, e ambos os chamadores já correm dentro de
  executores. Uma versão async obrigava a contorções nos dois lados.
* **Nunca levanta.** Corre depois de a resposta já ter ido para o cliente.
  Falhar a enviar um aviso não pode derrubar uma conversa nem impedir a tarefa
  de ser criada — a tarefa é a rede de segurança do email, não o contrário.

Canal decidido a 2026-08-15: email por agora, outro a confirmar. É esta função
que se troca nessa altura, não os sítios que a chamam.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # o SMTP não pode prender o turno; falhar depressa e seguir


def destinatarios() -> list[str]:
    return [e.strip() for e in settings.notificacoes_para.split(",") if e.strip()]


def configurado() -> bool:
    """Sem servidor ou sem destinatário, as notificações estão desligadas.

    Estado normal e não erro: permite ter isto em produção antes de existirem
    credenciais, e ligar sem novo deploy.
    """
    return bool(settings.smtp_host and destinatarios())


def notificar(assunto: str, corpo: str) -> None:
    """Manda o aviso. Engole tudo o que corra mal — ver docstring do módulo."""
    if not configurado():
        logger.debug("Notificações desligadas (sem smtp_host ou destinatário).")
        return

    try:
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = settings.smtp_user or "nao-responder@figueirahome.pt"
        msg["To"] = ", ".join(destinatarios())
        msg.set_content(corpo)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_TIMEOUT) as s:
            s.starttls()
            if settings.smtp_user and settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)

        logger.info("Notificação enviada: %s", assunto)
    except Exception:
        logger.exception("Falha ao notificar (%s) — a tarefa fica na mesma.", assunto)


def demo() -> None:
    """Auto-verificação das guardas. `python -m app.notificacoes` de `backend/`"""
    original = (settings.smtp_host, settings.notificacoes_para)
    try:
        settings.smtp_host, settings.notificacoes_para = "", ""
        assert configurado() is False
        notificar("x", "y")  # não pode levantar nem tentar ligar-se a nada

        settings.smtp_host, settings.notificacoes_para = "smtp.exemplo.pt", ""
        assert configurado() is False, "sem destinatário não está configurado"

        settings.notificacoes_para = " a@b.pt ,, c@d.pt "
        assert destinatarios() == ["a@b.pt", "c@d.pt"], destinatarios()
        assert configurado() is True

        # Host inexistente: tem de falhar em silêncio, não rebentar.
        settings.smtp_host = "servidor.que.nao.existe.invalido"
        notificar("teste", "corpo")
    finally:
        settings.smtp_host, settings.notificacoes_para = original

    print("notificacoes OK")


if __name__ == "__main__":
    demo()
