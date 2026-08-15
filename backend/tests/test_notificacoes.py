"""Notificação ao corretor — o que se testa são as guardas, não o envio.

Um aviso que falha não pode derrubar uma conversa nem impedir que a tarefa seja
criada: a tarefa é a rede de segurança do email, não o contrário. E com a
configuração vazia isto tem de ficar quieto, para poder estar em produção antes
de haver credenciais SMTP.

    pytest backend/tests/test_notificacoes.py      (a partir de `backend/`)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import notificacoes  # noqa: E402
from app.config import settings  # noqa: E402


def _configurar(monkeypatch, host="smtp.exemplo.pt", para="corretor@exemplo.pt"):
    monkeypatch.setattr(settings, "smtp_host", host)
    monkeypatch.setattr(settings, "notificacoes_para", para)
    monkeypatch.setattr(settings, "smtp_user", "u")
    monkeypatch.setattr(settings, "smtp_password", "p")


def test_sem_configuracao_nao_tenta_ligar_se(monkeypatch):
    """Estado normal até haver credenciais — não é erro, e não pode rebentar
    nem gerar tráfego."""
    _configurar(monkeypatch, host="", para="")

    def _explode(*a, **k):
        raise AssertionError("tentou ligar-se ao SMTP com a config vazia")

    monkeypatch.setattr(notificacoes.smtplib, "SMTP", _explode)

    assert notificacoes.configurado() is False
    notificacoes.notificar("assunto", "corpo")  # não levanta


def test_host_sem_destinatario_continua_desligado(monkeypatch):
    _configurar(monkeypatch, para="")
    assert notificacoes.configurado() is False


def test_destinatarios_aceita_lista(monkeypatch):
    monkeypatch.setattr(settings, "notificacoes_para", " a@b.pt ,, c@d.pt ")
    assert notificacoes.destinatarios() == ["a@b.pt", "c@d.pt"]


def test_falha_de_smtp_e_engolida(monkeypatch):
    """Corre depois de a resposta já ter ido para o cliente."""
    _configurar(monkeypatch)

    def _explode(*a, **k):
        raise OSError("servidor em baixo")

    monkeypatch.setattr(notificacoes.smtplib, "SMTP", _explode)
    notificacoes.notificar("assunto", "corpo")  # não levanta


def test_mensagem_leva_assunto_corpo_e_destinatarios(monkeypatch):
    _configurar(monkeypatch, para="a@b.pt, c@d.pt")
    enviadas = []

    class _SMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            enviadas.append(msg)

    monkeypatch.setattr(notificacoes.smtplib, "SMTP", _SMTP)
    notificacoes.notificar("Lead qualificada — Isabel", "Telefone: 912345678")

    assert len(enviadas) == 1
    msg = enviadas[0]
    assert msg["Subject"] == "Lead qualificada — Isabel"
    assert msg["To"] == "a@b.pt, c@d.pt"
    assert "912345678" in msg.get_content()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
