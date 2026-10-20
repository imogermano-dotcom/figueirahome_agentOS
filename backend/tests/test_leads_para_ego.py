"""Lead de compra sem resposta -> eGO (`docs/fases/lead-compra-para-ego-plano.md`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_leads_para_ego.py`.
Telefones de teste: `912345678`. Sem rede: Supabase e API do eGO são duplos.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.config import settings  # noqa: E402

AGORA = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
ISO = lambda h: (AGORA - timedelta(hours=h)).isoformat()  # noqa: E731


def _linha(**kw):
    base = {"id": "c1", "nome": "Teste", "telefone": "912345678", "telemovel": None, "email": "t@example.com",
            "meta_lead_id": "123", "imovel_ref": "FH0001", "ad_name": "Anúncio X", "template_enviado_em": ISO(3),
            "respondeu_em": None, "contacto_humano_em": None, "whatsapp_falhou_em": None}
    return base | kw


def test_template_ha_mais_de_2h_sem_resposta_e_elegivel():
    assert lp.elegivel(_linha(), AGORA)
    assert not lp.elegivel(_linha(template_enviado_em=ISO(1.9)), AGORA)


@pytest.mark.parametrize("campo", ["respondeu_em", "contacto_humano_em", "ego_lead_em"])
def test_quem_respondeu_ou_ja_tem_consultor_ou_ja_foi_tratada_nao_vai(campo):
    assert not lp.elegivel(_linha(**{campo: ISO(1)}), AGORA)
    assert not lp.elegivel(_linha(**{campo: ISO(1), "whatsapp_falhou_em": ISO(1)}), AGORA)


def test_numero_sem_whatsapp_vai_logo_mesmo_sem_template():
    assert lp.elegivel(_linha(template_enviado_em=None, whatsapp_falhou_em=ISO(0.1)), AGORA)


def test_sem_template_nem_falha_nao_vai():
    assert not lp.elegivel(_linha(template_enviado_em=None), AGORA)


def test_observacao_da_lead():
    o = lp.observacao_da_lead(_linha(whatsapp_falhou_em=ISO(1)), com_imovel=True)
    assert "Anúncio X" in o and "não recebeu" in o
    assert "FH0001" not in o, "com imóvel ligado a ref não vai no texto"
    assert "FH0001" in lp.observacao_da_lead(_linha(), com_imovel=False), "sem id do imóvel, a ref vai no texto"


def test_ja_nas_leads_por_telefone_ou_email():
    assert lp._ja_nas_leads(_linha(), [{"phone": "+351912345678", "email": None}])
    assert lp._ja_nas_leads(_linha(telefone="900000000"), [{"phone": None, "email": "T@Example.com"}])
    assert not lp._ja_nas_leads(_linha(), [{"phone": "933333333", "email": "outro@example.com"}])


class _BD:
    """Duplo de `contactos` + `oportunidades`; regista os updates."""

    def __init__(self, contactos, oportunidade=False):
        self.contactos, self.oportunidade, self.updates, self._t, self._upd = contactos, oportunidade, [], None, None

    def table(self, nome):
        self._t, self._upd = nome, None
        return self

    def __getattr__(self, nome):  # filtros encadeados são irrelevantes para o duplo
        if nome == "not_":
            return self
        return lambda *a, **k: self

    def update(self, valores):
        self._upd = valores
        return self

    def eq(self, _, valor):
        if self._upd is not None:
            self.updates.append((valor, self._upd))
        return self

    def execute(self):
        if self._t == "oportunidades":
            return type("R", (), {"data": [{"oportunidade_ref": "x", "responsavel": "Ana Teste"}] if self.oportunidade else []})()
        return type("R", (), {"data": self.contactos})()


def _usa(monkeypatch, bd, enviar, leads=()):
    monkeypatch.setattr(lp, "get_supabase", lambda: bd)
    monkeypatch.setattr(lp.egorealestate, "inserir_lead_webapi", enviar)
    monkeypatch.setattr(lp.ego_api, "leads_abertas", lambda: list(leads))
    monkeypatch.setattr(lp, "_ego_id_do_imovel", lambda ref: 30640811)
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")


def test_desligado_com_data_vazia(monkeypatch):
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "")
    monkeypatch.setattr(lp, "get_supabase", lambda: pytest.fail("não devia tocar na BD"))
    assert lp.processar(AGORA) == {"ativo": False}


def test_cria_e_marca(monkeypatch):
    bd = _BD([_linha()])
    _usa(monkeypatch, bd, lambda *a: "555")
    r = lp.processar(AGORA)
    assert (r["criadas"], r["erros"]) == (1, 0)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat(), "ego_lead_id": 555})]


def test_pessoa_com_oportunidade_ativa_nao_cria_mas_marca(monkeypatch):
    bd = _BD([_linha()], oportunidade=True)
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    r = lp.processar(AGORA)
    assert r["ja_existiam"] == 1 and bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat()})]


def test_pessoa_ja_na_caixa_de_leads_nao_cria_mas_marca(monkeypatch):
    bd = _BD([_linha()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"), leads=[{"phone": "+351912345678"}])
    r = lp.processar(AGORA)
    assert r["ja_existiam"] == 1 and bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat()})]


def test_sem_conseguir_ler_as_leads_nao_cria_nada(monkeypatch):
    bd = _BD([_linha()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))

    def _rebenta():
        raise RuntimeError("503")
    monkeypatch.setattr(lp.ego_api, "leads_abertas", _rebenta)
    r = lp.processar(AGORA)
    assert r["erros"] == 1 and r["criadas"] == 0 and bd.updates == []


def test_falha_da_api_nao_marca(monkeypatch):
    bd = _BD([_linha()])

    def _rebenta(*a):
        raise RuntimeError("403")
    _usa(monkeypatch, bd, _rebenta)
    r = lp.processar(AGORA)
    assert r["erros"] == 1 and bd.updates == []


def test_resposta_sem_id_marca_na_mesma(monkeypatch):
    """HTTP 2xx = criada; repetir criava duplicado."""
    bd = _BD([_linha()])
    _usa(monkeypatch, bd, lambda *a: None)
    lp.processar(AGORA)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat()})]


def test_envia_os_campos_da_web_api(monkeypatch):
    bd = _BD([_linha(whatsapp_falhou_em=ISO(1))])
    recebido = []
    _usa(monkeypatch, bd, lambda *a: recebido.append(a))
    lp.processar(AGORA)
    nome, email, tel, obs, ego_id = recebido[0]
    assert (nome, email, tel, ego_id) == ("Teste", "t@example.com", "912345678", 30640811)
    assert "Anúncio X" in obs and "FH0001" not in obs


def test_web_api_put_com_query_do_make(monkeypatch):
    from app.integrations import egorealestate as eg

    visto = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"ID": 77}

    def put(url, headers=None, params=None, timeout=None):
        visto.update(url=url, params=params, headers=headers)
        return R()

    monkeypatch.setattr(eg.httpx, "put", put)
    assert eg.inserir_lead_webapi("Ana", "a@example.com", "912345678", "obs", 25352543) == "77"
    assert visto["url"].endswith("/v1/Lead")
    assert visto["params"] == {"CTY": 4, "NAM": "Ana", "EML": "a@example.com", "PHO": "912345678", "OBS": "obs",
                               "RID": 25352543}
    assert "AuthorizationToken" in visto["headers"]
    visto.clear()
    eg.inserir_lead_webapi("Ana", None, None, "obs", None)
    assert "RID" not in visto["params"] and visto["params"]["EML"] == ""


# ── recusou o WhatsApp: vai logo, a par do email (n8n) ─────────────────────────────────────────────────────────


def _recusa(monkeypatch, linha=None, *, responsavel=None, caixa=(), ler_rebenta=False, conhecido=False):
    bd = _BD([linha or _linha(template_enviado_em=None, meta_lead_id="m1")])
    enviados = []

    def ler():
        if ler_rebenta:
            raise RuntimeError("eGO em baixo")
        return list(caixa)

    monkeypatch.setattr(lp, "get_supabase", lambda: bd)
    monkeypatch.setattr(lp.ego_api, "leads_abertas", ler)
    monkeypatch.setattr(lp, "_responsavel_da_oportunidade", lambda tel, email=None: responsavel)
    monkeypatch.setattr(lp, "_email_do_responsavel", lambda nome: "ana@example.com" if nome else None)
    monkeypatch.setattr(lp, "_contacto_conhecido", lambda linha, tel: conhecido)
    monkeypatch.setattr(lp, "_ego_id_do_imovel", lambda ref: 30640811)
    monkeypatch.setattr(lp.egorealestate, "inserir_lead_webapi", lambda *a: enviados.append(a))
    return bd, enviados


def test_recusa_sem_historico_cria_logo_sem_esperar(monkeypatch):
    bd, enviados = _recusa(monkeypatch)  # sem template nem tempo de espera
    r = lp.recusou_whatsapp("m1")
    assert r["resultado"] == "criada" and r["criada"] and r["verificado_no_ego"]
    assert len(enviados) == 1 and "recusou o WhatsApp" in enviados[0][3] and enviados[0][4] == 30640811
    assert bd.updates and "ego_lead_em" in bd.updates[0][1]


def test_recusa_de_pessoa_com_oportunidade_ativa_nao_cria_e_diz_a_quem_avisar(monkeypatch):
    bd, enviados = _recusa(monkeypatch, responsavel="Ana Teste")
    r = lp.recusou_whatsapp("m1")
    assert r["resultado"] == "oportunidade_ativa" and not r["criada"]
    assert (r["responsavel"], r["email_responsavel"]) == ("Ana Teste", "ana@example.com")
    assert enviados == [] and bd.updates, "marca para o n8n não repetir"


def test_recusa_de_pessoa_ja_na_caixa_de_leads_nao_cria(monkeypatch):
    _, enviados = _recusa(monkeypatch, caixa=[{"phone": "+351912345678"}])
    assert lp.recusou_whatsapp("m1")["resultado"] == "ja_na_caixa" and enviados == []


def test_recusa_de_contacto_antigo_cria_e_diz_que_ja_existia(monkeypatch):
    _, enviados = _recusa(monkeypatch, conhecido=True)
    assert lp.recusou_whatsapp("m1")["criada"] and "já existente no eGO" in enviados[0][3]


def test_recusa_com_eGO_em_baixo_cria_na_mesma_e_diz_que_nao_verificou(monkeypatch):
    _, enviados = _recusa(monkeypatch, ler_rebenta=True)
    r = lp.recusou_whatsapp("m1")
    assert r["criada"] and r["verificado_no_ego"] is False and len(enviados) == 1


def test_recusa_ja_tratada_nao_repete(monkeypatch):
    _, enviados = _recusa(monkeypatch, linha=_linha(ego_lead_em=ISO(1), meta_lead_id="m1"))
    assert lp.recusou_whatsapp("m1") == {"resultado": "ja_tratada"} and enviados == []


def test_recusa_de_contacto_inexistente(monkeypatch):
    monkeypatch.setattr(lp, "get_supabase", lambda: _BD([]))
    assert lp.recusou_whatsapp("nao-existe") is None


def test_falha_do_put_nao_marca_e_levanta(monkeypatch):
    bd, _ = _recusa(monkeypatch)

    def rebenta(*a):
        raise RuntimeError("PUT falhou")

    monkeypatch.setattr(lp.egorealestate, "inserir_lead_webapi", rebenta)
    with pytest.raises(RuntimeError):
        lp.recusou_whatsapp("m1")
    assert bd.updates == []


def test_endpoint_da_recusa_exige_segredo_e_devolve_404(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import require_n8n_access
    from app.main import app

    url = "/api/leads/meta/m1/recusou-whatsapp"
    assert TestClient(app).post(url).status_code == 401
    app.dependency_overrides[require_n8n_access] = lambda: "teste"
    try:
        monkeypatch.setattr(lp, "recusou_whatsapp", lambda mid: None)
        assert TestClient(app).post(url).status_code == 404
        monkeypatch.setattr(lp, "recusou_whatsapp", lambda mid: {"resultado": "criada"})
        assert TestClient(app).post(url).json() == {"resultado": "criada"}
    finally:
        app.dependency_overrides.clear()


def test_segredo_do_n8n_abre_so_o_endpoint_da_recusa(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(settings, "n8n_secret", "segredo-n8n")
    monkeypatch.setattr(settings, "automacao_secret", "outro-segredo")
    monkeypatch.setattr(lp, "recusou_whatsapp", lambda mid: {"resultado": "criada"})
    c = TestClient(app)
    recusa = "/api/leads/meta/m1/recusou-whatsapp"
    assert c.post(recusa, headers={"X-N8N-Secret": "segredo-n8n"}).status_code == 200
    assert c.post(recusa, headers={"X-N8N-Secret": "errado"}).status_code == 401
    assert c.post(recusa, headers={"X-Automacao-Secret": "outro-segredo"}).status_code == 200  # o de antes continua
    # o segredo do n8n não abre os outros endpoints de automação
    assert c.post("/api/leads/meta/para-ego", headers={"X-N8N-Secret": "segredo-n8n"}).status_code == 401


def test_segredo_do_n8n_vazio_nunca_autentica(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(settings, "n8n_secret", "")
    monkeypatch.setattr(settings, "automacao_secret", "")
    r = TestClient(app).post("/api/leads/meta/m1/recusou-whatsapp", headers={"X-N8N-Secret": ""})
    assert r.status_code == 401


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
