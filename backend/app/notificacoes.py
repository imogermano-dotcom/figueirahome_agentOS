"""Aviso ao corretor quando acontece algo que não pode esperar pelo painel.

Antes disto, uma lead qualificada e um escalamento acabavam ambos numa linha em
`agente_tarefas` e mais nada — se ninguém abrisse o painel, a lead paga que
qualificou às 23h ficava lá até alguém reparar. Uma lead imobiliária é
perecível; a tarefa continua a ser o registo, isto é o toque no ombro.

**Microsoft Graph, não SMTP** (decidido 2026-08-16). O correio da agência é
Microsoft 365, e a Microsoft está a extinguir o SMTP AUTH no Exchange Online —
construir em cima dele era garantir que se refazia isto mais tarde. A Graph é o
caminho suportado. Sem dependências novas: `httpx` já cá estava.

Três decisões que se mantêm da versão SMTP:

* **Uma só função pública.** Trocar de canal — foi o que aconteceu — mexe aqui e
  em mais lado nenhum. Os dois sítios que notificam não souberam da mudança.
* **Síncrona.** Ambos os chamadores já correm dentro de executores; uma versão
  async obrigava a contorções nos dois.
* **Nunca levanta.** Corre depois de a resposta já ter ido para o cliente.
  Falhar a enviar um aviso não pode derrubar uma conversa nem impedir a tarefa
  de ser criada — a tarefa é a rede de segurança do email, não o contrário.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # o envio não pode prender o turno; falhar depressa e seguir

# Token de client credentials, válido ~1h. Sem cache era um pedido de token por
# cada aviso — o dobro das chamadas e do tempo, para nada.
_token: dict = {"valor": None, "expira_em": 0.0}
_MARGEM = 60  # renovar antes de expirar, para não apanhar a fronteira


def destinatarios() -> list[str]:
    return [e.strip() for e in settings.notificacoes_para.split(",") if e.strip()]


def configurado() -> bool:
    """Sem app registada ou sem destinatário, as notificações estão desligadas.

    Estado normal e não erro: permite ter isto em produção antes de existirem
    credenciais, e ligar sem novo deploy.
    """
    return bool(
        settings.graph_tenant_id
        and settings.graph_client_id
        and settings.graph_client_secret
        and settings.graph_remetente
        and destinatarios()
    )


def _obter_token() -> str:
    if _token["valor"] and time.time() < _token["expira_em"]:
        return _token["valor"]

    resp = httpx.post(
        f"https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    dados = resp.json()
    _token["valor"] = dados["access_token"]
    _token["expira_em"] = time.time() + dados.get("expires_in", 3600) - _MARGEM
    return _token["valor"]


def notificar(assunto: str, corpo: str) -> None:
    """Manda o aviso. Engole tudo o que corra mal — ver docstring do módulo."""
    if not configurado():
        logger.debug("Notificações desligadas (sem app Graph ou destinatário).")
        return

    try:
        resp = httpx.post(
            f"https://graph.microsoft.com/v1.0/users/{settings.graph_remetente}/sendMail",
            headers={"Authorization": f"Bearer {_obter_token()}"},
            json={
                "message": {
                    "subject": assunto,
                    "body": {"contentType": "Text", "content": corpo},
                    "toRecipients": [
                        {"emailAddress": {"address": e}} for e in destinatarios()
                    ],
                },
                # Não guardar em Enviados: são avisos de máquina, e enchiam a
                # caixa de quem envia sem acrescentar nada.
                "saveToSentItems": False,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Notificação enviada: %s", assunto)
    except httpx.HTTPStatusError as e:
        # O corpo da Graph diz o que falhou (permissão em falta, mailbox sem
        # licença, remetente inexistente); sem ele o diagnóstico é adivinhar.
        logger.error(
            "Falha ao notificar (%s): HTTP %s — %s",
            assunto, e.response.status_code, e.response.text[:300],
        )
        _token["valor"] = None  # pode ser token inválido; forçar renovação
    except Exception:
        logger.exception("Falha ao notificar (%s) — a tarefa fica na mesma.", assunto)


def demo() -> None:
    """Auto-verificação das guardas. `python -m app.notificacoes` de `backend/`"""
    original = (
        settings.graph_tenant_id, settings.graph_client_id,
        settings.graph_client_secret, settings.graph_remetente,
        settings.notificacoes_para,
    )
    try:
        settings.graph_tenant_id = settings.graph_client_id = ""
        settings.graph_client_secret = settings.graph_remetente = ""
        settings.notificacoes_para = ""
        assert configurado() is False
        notificar("x", "y")  # não pode levantar nem gerar tráfego

        settings.graph_tenant_id = "t"
        settings.graph_client_id = "c"
        settings.graph_client_secret = "s"
        settings.graph_remetente = "avisos@exemplo.pt"
        assert configurado() is False, "sem destinatário continua desligado"

        settings.notificacoes_para = " a@b.pt ,, c@d.pt "
        assert destinatarios() == ["a@b.pt", "c@d.pt"], destinatarios()
        assert configurado() is True

        # Tenant inexistente: tem de falhar em silêncio, não rebentar.
        settings.graph_tenant_id = "tenant-que-nao-existe.invalido"
        notificar("teste", "corpo")
    finally:
        (settings.graph_tenant_id, settings.graph_client_id,
         settings.graph_client_secret, settings.graph_remetente,
         settings.notificacoes_para) = original
        _token["valor"], _token["expira_em"] = None, 0.0

    print("notificacoes OK")


if __name__ == "__main__":
    demo()
