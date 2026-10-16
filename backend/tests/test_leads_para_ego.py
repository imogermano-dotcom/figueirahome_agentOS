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


def test_corpo_da_lead():
    c = lp.corpo_da_lead(_linha(whatsapp_falhou_em=ISO(1)))
    assert (c["originId"], c["subOriginId"], c["typeId"], c["masterLeadTypeId"]) == (1, 4001, 7, 2)
    assert c["externalId"] == "123" and c["phone"] == "912345678" and c["labels"] == []
    assert "FH0001" in c["observation"] and "não recebeu" in c["observation"]


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
            return type("R", (), {"data": [{"oportunidade_ref": "x"}] if self.oportunidade else []})()
        return type("R", (), {"data": self.contactos})()


def _usa(monkeypatch, bd, enviar):
    monkeypatch.setattr(lp, "get_supabase", lambda: bd)
    monkeypatch.setattr(lp.ego_api, "inserir_lead", enviar)
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")


def test_desligado_com_data_vazia(monkeypatch):
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "")
    monkeypatch.setattr(lp, "get_supabase", lambda: pytest.fail("não devia tocar na BD"))
    assert lp.processar(AGORA) == {"ativo": False}


def test_cria_e_marca(monkeypatch):
    bd = _BD([_linha()])
    _usa(monkeypatch, bd, lambda corpo: 555)
    r = lp.processar(AGORA)
    assert (r["criadas"], r["erros"]) == (1, 0)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat(), "ego_lead_id": 555})]


def test_pessoa_com_oportunidade_ativa_nao_cria_mas_marca(monkeypatch):
    bd = _BD([_linha()], oportunidade=True)
    _usa(monkeypatch, bd, lambda corpo: pytest.fail("não devia criar"))
    r = lp.processar(AGORA)
    assert r["ja_existiam"] == 1 and bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat()})]


def test_falha_da_api_nao_marca(monkeypatch):
    bd = _BD([_linha()])

    def _rebenta(corpo):
        raise RuntimeError("403")
    _usa(monkeypatch, bd, _rebenta)
    r = lp.processar(AGORA)
    assert r["erros"] == 1 and bd.updates == []


def test_resposta_sem_id_marca_na_mesma(monkeypatch):
    """HTTP 2xx = criada; repetir criava duplicado."""
    bd = _BD([_linha()])
    _usa(monkeypatch, bd, lambda corpo: None)
    lp.processar(AGORA)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat(), "ego_lead_id": None})]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
