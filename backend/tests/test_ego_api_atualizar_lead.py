"""`ego_api.atualizar_lead`: o `UpdateLead` do eGO SUBSTITUI a lead (corpo só com `id` + observações apagou título, email e
telefone, 22/10), por isso o corpo parte do `GetLead` completo. Sem rede."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations import ego_api  # noqa: E402

LEAD = {"id": 7, "title": "T", "name": "N", "email": "t@example.com", "phone": "912345678", "obs": "texto",
        "originId": 11, "leadSubOriginId": 34798477, "leadTypeId": 4, "masterTypeId": 2, "realestateId": None,
        "assignToSecurityUserId": None, "assignToSecurityUserIds": [], "alterDate": "2026-10-22T08:00:00",
        "leadOrigin": {"id": 11, "name": "Outros"}, "leadProbabilitySucess": 0, "securityUserId": 92411}


def test_corpo_leva_tudo_do_get_lead_com_os_nomes_de_escrita():
    c = ego_api.corpo_de_atualizacao(LEAD)
    assert (c["title"], c["email"], c["phone"], c["name"]) == ("T", "t@example.com", "912345678", "N")
    assert (c["observation"], c["typeId"], c["masterLeadTypeId"], c["subOriginId"]) == ("texto", 4, 2, 34798477)
    assert "obs" not in c and "leadTypeId" not in c and "masterTypeId" not in c
    assert c["leadProbabilitySuccess"] == 0 and "leadProbabilitySucess" not in c
    assert "leadOrigin" not in c, "objetos aninhados são só de leitura"
    assert c["labels"] == [] and c["assignToSecurityUserIDList"] == [], "as 16 listas obrigatórias seguem sempre"


def test_mudancas_sobrepoem_e_o_resto_fica_igual():
    c = ego_api.corpo_de_atualizacao(LEAD, assignToSecurityUserId=77529, assignToSecurityUserIDList=[77529], realestateId=31173280)
    assert c["assignToSecurityUserId"] == 77529 and c["assignToSecurityUserIDList"] == [77529] and c["realestateId"] == 31173280
    assert (c["title"], c["email"], c["phone"]) == ("T", "t@example.com", "912345678")


class _Resp:
    def __init__(self, dados, status=200):
        self._d, self.status_code, self.content = dados, status, b"x"
        self.request = type("R", (), {"url": type("U", (), {"path": "/x"})()})()

    def json(self):
        return self._d


class _Cliente:
    """GetLead devolve o estado atual; o PUT aplica o corpo como o eGO (campos em falta ficam vazios)."""

    def __init__(self, lead, resposta_put=7, aplica=True):
        self.lead, self.resposta_put, self.aplica, self.puts = dict(lead), resposta_put, aplica, []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def get(self, url, **kw):
        return _Resp(dict(self.lead))

    def put(self, url, params=None, json=None, headers=None):
        self.puts.append(json)
        if self.aplica:
            if json.get("assignToSecurityUserId") is not None:
                self.lead["assignToSecurityUserId"] = json["assignToSecurityUserId"]
            if json.get("realestateId") is not None:
                self.lead["realestateId"] = json["realestateId"]
        return _Resp(self.resposta_put)


def _usa(monkeypatch, cliente):
    monkeypatch.setattr(ego_api.httpx, "Client", lambda **kw: cliente)
    monkeypatch.setattr(ego_api, "_sessao_valida", lambda c: {"token": "t", "application_id": 6429, "security_user_id": 92411})


def test_atualizar_devolve_o_que_mudou(monkeypatch):
    cl = _Cliente(LEAD)
    _usa(monkeypatch, cl)
    mudou = ego_api.atualizar_lead(7, assignToSecurityUserId=77529, assignToSecurityUserIDList=[77529], realestateId=31173280)
    assert mudou == {"assignToSecurityUserId": (None, 77529), "realestateId": (None, 31173280)}
    assert cl.puts[0]["id"] == 7 and cl.puts[0]["title"] == "T", "o corpo leva o título: o PUT substitui a lead"


def test_resposta_zero_levanta(monkeypatch):
    _usa(monkeypatch, _Cliente(LEAD, resposta_put=0))
    with pytest.raises(ego_api.EgoApiErro, match="não alterou nada"):
        ego_api.atualizar_lead(7, realestateId=1)


def test_mudar_algo_que_nao_se_pediu_levanta(monkeypatch):
    class Estraga(_Cliente):
        def put(self, url, params=None, json=None, headers=None):
            r = super().put(url, params, json, headers)
            self.lead["email"] = None  # o eGO apagou o email
            return r

    _usa(monkeypatch, Estraga(LEAD))
    with pytest.raises(ego_api.EgoApiErro, match="mudou campos que não pediste"):
        ego_api.atualizar_lead(7, realestateId=1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
