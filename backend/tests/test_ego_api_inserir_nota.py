"""`ego_api.inserir_nota` (pedido #17, fase 2): nota na lead (14) ou, depois da promoção, na oportunidade (3, mesmo id). Sem rede."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations import ego_api  # noqa: E402


class _Resp:
    def __init__(self, dados, status=200):
        self._d, self.status_code, self.content = dados, status, b"x"
        self.request = type("R", (), {"url": type("U", (), {"path": "/x"})()})()

    def json(self):
        return self._d


class _Cliente:
    def __init__(self, resposta=777, status=200):
        self.resposta, self.status, self.posts = resposta, status, []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def post(self, url, params=None, json=None, headers=None):
        self.posts.append((url, params, json))
        return _Resp(self.resposta, self.status)


def _preparar(monkeypatch, *, lead, cliente):
    monkeypatch.setattr(ego_api, "_pedido", lambda metodo, caminho, **kw: lead)
    monkeypatch.setattr(ego_api.httpx, "Client", lambda **kw: cliente)
    monkeypatch.setattr(ego_api, "_sessao_valida", lambda c: {"token": "t", "application_id": 6429, "security_user_id": 92411})


def test_lead_ainda_nao_promovida_escreve_com_objeto_14(monkeypatch):
    c = _Cliente()
    _preparar(monkeypatch, lead={"id": 61054906, "upgradeUserID": None}, cliente=c)
    r = ego_api.inserir_nota(61054906, "  A pessoa respondeu.  ")
    assert r == {"objeto": 14, "nota_id": 777}
    url, params, corpo = c.posts[0]
    assert url.endswith("/note/Note/InsertNote") and params == {"applicationId": 6429}
    assert corpo == {"objectId": 61054906, "objectName": 14, "description": "A pessoa respondeu.", "securityUserId": 92411, "applicationId": 6429}


def test_lead_promovida_escreve_na_oportunidade_com_o_mesmo_id(monkeypatch):
    c = _Cliente(resposta={"id": "55"})
    _preparar(monkeypatch, lead={"id": 61054906, "upgradeUserID": 51779}, cliente=c)
    assert ego_api.inserir_nota(61054906, "x") == {"objeto": 3, "nota_id": 55}
    assert c.posts[0][2]["objectName"] == 3 and c.posts[0][2]["objectId"] == 61054906


@pytest.mark.parametrize("resposta", [0, "", None, {"ok": True}, "abc"])
def test_resposta_sem_id_da_nota_levanta(monkeypatch, resposta):
    _preparar(monkeypatch, lead={"upgradeUserID": None}, cliente=_Cliente(resposta=resposta))
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.inserir_nota(1, "x")


def test_http_de_erro_levanta(monkeypatch):
    _preparar(monkeypatch, lead={"upgradeUserID": None}, cliente=_Cliente(status=400))
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.inserir_nota(1, "x")


@pytest.mark.parametrize("texto", ["", "   ", None])
def test_nota_vazia_nao_chega_ao_eGO(monkeypatch, texto):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: pytest.fail("não devia ler a lead"))
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.inserir_nota(1, texto)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
