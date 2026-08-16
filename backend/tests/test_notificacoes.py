"""Notificação ao corretor — o que se testa são as guardas, não o envio.

Um aviso que falha não pode derrubar uma conversa nem impedir que a tarefa seja
criada: a tarefa é a rede de segurança do email, não o contrário. E com a
configuração vazia isto tem de ficar quieto, para poder estar em produção antes
de existirem credenciais.

    pytest backend/tests/test_notificacoes.py      (a partir de `backend/`)
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import notificacoes  # noqa: E402
from app.config import settings  # noqa: E402


def _configurar(monkeypatch, tenant="t1", para="corretor@exemplo.pt"):
    monkeypatch.setattr(settings, "graph_tenant_id", tenant)
    monkeypatch.setattr(settings, "graph_client_id", "c1")
    monkeypatch.setattr(settings, "graph_client_secret", "s1")
    monkeypatch.setattr(settings, "graph_remetente", "avisos@exemplo.pt")
    monkeypatch.setattr(settings, "notificacoes_para", para)
    monkeypatch.setattr(notificacoes, "_token", {"valor": None, "expira_em": 0.0})


def test_sem_configuracao_nao_gera_trafego(monkeypatch):
    """Estado normal até haver credenciais — não é erro, e não pode rebentar."""
    _configurar(monkeypatch, tenant="", para="")

    def _explode(*a, **k):
        raise AssertionError("tentou chamar a Graph com a config vazia")

    monkeypatch.setattr(notificacoes.httpx, "post", _explode)
    assert notificacoes.configurado() is False
    notificacoes.notificar("assunto", "corpo")


def test_sem_destinatario_continua_desligado(monkeypatch):
    _configurar(monkeypatch, para="")
    assert notificacoes.configurado() is False


def test_destinatarios_aceita_lista(monkeypatch):
    monkeypatch.setattr(settings, "notificacoes_para", " a@b.pt ,, c@d.pt ")
    assert notificacoes.destinatarios() == ["a@b.pt", "c@d.pt"]


def test_falha_da_graph_e_engolida(monkeypatch):
    """Corre depois de a resposta já ter ido para o cliente."""
    _configurar(monkeypatch)

    def _explode(*a, **k):
        raise httpx.ConnectError("rede em baixo")

    monkeypatch.setattr(notificacoes.httpx, "post", _explode)
    notificacoes.notificar("assunto", "corpo")  # não levanta


def test_erro_http_nao_levanta_e_invalida_o_token(monkeypatch):
    """403 por falta de consentimento é o erro mais provável na estreia. Tem de
    ficar no log, não derrubar a conversa — e o token cai, porque pode ser ele."""
    _configurar(monkeypatch)
    notificacoes._token["valor"] = "token-velho"
    notificacoes._token["expira_em"] = 9e12

    def _post(url, **k):
        pedido = httpx.Request("POST", url)
        return httpx.Response(403, text="Insufficient privileges", request=pedido)

    monkeypatch.setattr(notificacoes.httpx, "post", _post)
    notificacoes.notificar("assunto", "corpo")
    assert notificacoes._token["valor"] is None


def test_mensagem_bem_formada_e_token_reutilizado(monkeypatch):
    _configurar(monkeypatch, para="a@b.pt, c@d.pt")
    chamadas = []

    def _post(url, **k):
        chamadas.append((url, k))
        pedido = httpx.Request("POST", url)
        if "oauth2" in url:
            return httpx.Response(
                200, json={"access_token": "tok", "expires_in": 3600}, request=pedido
            )
        return httpx.Response(202, request=pedido)

    monkeypatch.setattr(notificacoes.httpx, "post", _post)

    notificacoes.notificar("Lead qualificada — Isabel", "Telefone: 912345678")
    notificacoes.notificar("Segundo aviso", "corpo")

    urls = [u for u, _ in chamadas]
    assert sum("oauth2" in u for u in urls) == 1, "pediu token duas vezes — cache partida"
    assert sum("sendMail" in u for u in urls) == 2

    _, kwargs = chamadas[1]
    msg = kwargs["json"]["message"]
    assert msg["subject"] == "Lead qualificada — Isabel"
    assert "912345678" in msg["body"]["content"]
    assert [d["emailAddress"]["address"] for d in msg["toRecipients"]] == ["a@b.pt", "c@d.pt"]
    assert kwargs["json"]["saveToSentItems"] is False
    assert kwargs["headers"]["Authorization"] == "Bearer tok"


def _capturar(monkeypatch):
    """Devolve a lista de chamadas httpx.post, com o token já resolvido."""
    chamadas = []

    def _post(url, **k):
        chamadas.append((url, k))
        pedido = httpx.Request("POST", url)
        if "oauth2" in url:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600},
                                  request=pedido)
        return httpx.Response(202, request=pedido)

    monkeypatch.setattr(notificacoes.httpx, "post", _post)
    return chamadas


def _para(chamadas):
    _, k = [c for c in chamadas if "sendMail" in c[0]][0]
    return [d["emailAddress"]["address"] for d in k["json"]["message"]["toRecipients"]]


def test_consultor_do_imovel_entra_nos_destinatarios(monkeypatch):
    """A lead vem do anúncio de um imóvel; quem o angariou tem de saber."""
    _configurar(monkeypatch, para="director@figueirahome.pt")
    chamadas = _capturar(monkeypatch)
    monkeypatch.setattr(
        notificacoes, "_consultor_do_imovel",
        lambda ref: ("alexandra.santos@figueirahome.pt", "Alexandra Santos"),
    )

    notificacoes.notificar("Lead qualificada", "corpo", imovel_ref="FH2581")

    assert _para(chamadas) == ["director@figueirahome.pt", "alexandra.santos@figueirahome.pt"]


def test_sem_consultora_vai_so_ao_director_e_diz_porque(monkeypatch):
    """39% dos imóveis publicados estavam atribuídos a quem já saiu da agência
    (2026-08-16). O aviso não se perde — vai ao director — e o corpo diz que o
    imóvel precisa de reatribuição, não que falte configurar alguma coisa."""
    _configurar(monkeypatch, para="director@figueirahome.pt")
    chamadas = _capturar(monkeypatch)
    motivo = ("o imóvel FH2450 está atribuído a Lina Galvão, que não tem "
              "consultora activa associada — reatribuir no eGO")
    monkeypatch.setattr(notificacoes, "_consultor_do_imovel", lambda ref: (None, motivo))

    notificacoes.notificar("Lead qualificada", "corpo", imovel_ref="FH2450")

    assert _para(chamadas) == ["director@figueirahome.pt"]
    _, k = [c for c in chamadas if "sendMail" in c[0]][0]
    corpo = k["json"]["message"]["body"]["content"]
    assert "reatribuir no eGO" in corpo
    # Nunca sugerir criar perfil: levaria alguém a criar contas a quem já saiu.
    assert "profiles" not in corpo


def test_consultor_que_e_o_director_nao_duplica(monkeypatch):
    _configurar(monkeypatch, para="miguel.germano@figueirahome.pt")
    chamadas = _capturar(monkeypatch)
    monkeypatch.setattr(
        notificacoes, "_consultor_do_imovel",
        lambda ref: ("miguel.germano@figueirahome.pt", "Miguel Germano"),
    )

    notificacoes.notificar("Lead qualificada", "corpo", imovel_ref="FH2400")

    assert _para(chamadas) == ["miguel.germano@figueirahome.pt"]


def test_sem_imovel_nao_procura_consultor(monkeypatch):
    """Escalamentos sem imóvel associado não podem gastar duas consultas."""
    _configurar(monkeypatch, para="director@figueirahome.pt")
    chamadas = _capturar(monkeypatch)

    def _nao_chamar(ref):
        raise AssertionError("procurou consultor sem imovel_ref")

    monkeypatch.setattr(notificacoes, "_consultor_do_imovel", _nao_chamar)
    notificacoes.notificar("Escalado", "corpo")
    assert _para(chamadas) == ["director@figueirahome.pt"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
