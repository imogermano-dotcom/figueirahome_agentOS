"""Visitas pela API do eGO (P2, `docs/fases/api-a-substituir-scraper-acelerado-plano.md`, 26/11).

Nomes e referências de teste: `Pessoa Teste`, `Dono Teste`, `FH0001`. Sem rede: Supabase e a API são duplos.
"""

import pytest

from app.integrations import visitas_api as va


def _v(ref="VF_1", **extra):
    return {
        "visitReference": ref, "leadId": 1, "realestateId": 10, "date": "2026-11-13T00:00:00", "cancelled": False, "interested": 2173,
        "positivePoints": [5, 19853], "negativePoints": [20922], "aboutBusiness": [], "potencialClientName": "Pessoa Teste",
        "ownerName": "Dono Teste", "observations": " Gostou ", "securityUserId": 3, **extra,
    }


def test_linha_traduz_ids_data_e_anulada():
    linha = va.linha_de_visita(_v(), "VEN_1", "FH0001", {3: "Consultora Teste"}, "Outra Teste")
    assert linha == {
        "visita_ref_ego": "VF_1", "oportunidade_ref": "VEN_1", "visita_imovel_ref": "FH0001", "visita_data": "2026-11-13", "visita_anulada": "Não",
        "visita_interessado": "Interessado", "visita_cliente": "Pessoa Teste", "visita_imovel_proprietario": "Dono Teste",
        "visita_pontos_positivos": "Boa localização, Garagem", "visita_pontos_negativos": "investimento avultado",
        "visita_observacoes": "Gostou", "visita_responsavel": "Consultora Teste",
    }
    assert va.linha_de_visita(_v(cancelled=True), "VEN_1", None, {}, None)["visita_anulada"] == "Sim"


def test_responsavel_cai_para_o_da_oportunidade_quando_o_utilizador_saiu():
    assert va.linha_de_visita(_v(securityUserId=999), "VEN_1", None, {3: "Consultora Teste"}, "Outra Teste")["visita_responsavel"] == "Outra Teste"
    assert "visita_responsavel" not in va.linha_de_visita(_v(securityUserId=999), "VEN_1", None, {}, None)


def test_id_desconhecido_salta_e_conta_sem_gravar_o_codigo():
    d: list = []
    linha = va.linha_de_visita(_v(positivePoints=[5, 15815], interested=777), "VEN_1", None, {}, None, d)
    assert linha["visita_pontos_positivos"] == "Boa localização" and "visita_interessado" not in linha
    assert sorted(d) == [777, 15815]
    assert "15815" not in str(linha) and "777" not in str(linha)


def test_planear_insere_as_novas_completa_so_os_vazios_e_nunca_sobrescreve():
    existente = {"visita_ref_ego": "VF_1", "oportunidade_ref": "VEN_1", "visita_data": "2026-11-13", "visita_anulada": "Não", "visita_cliente": "Pessoa Teste",
                 "visita_imovel_ref": "FH0001", "visita_interessado": "Pouco Interessado", "visita_observacoes": None}
    api = [_v("VF_1"), _v("VF_2"), _v("VF_3", leadId=99)]
    p = va.planear(api, {"VF_1": existente}, {"VEN_1"}, {1: "VEN_1", 99: "VEN_9"}, {10: "FH0001"}, {3: "Consultora Teste"}, {})
    assert [x["visita_ref_ego"] for x in p["novas"]] == ["VF_2"]
    assert p["sem_oportunidade"] == 1, "VEN_9 ainda não está em oportunidades"
    assert p["completar"]["VF_1"]["visita_observacoes"] == "Gostou" and "visita_interessado" not in p["completar"]["VF_1"], "o que a BD já tem não se toca"
    assert p["divergentes"] == {"visita_interessado": 1}, "a BD tem outro valor: conta, não altera"


class _BD:
    def __init__(self, erro=None):
        self.erro, self.inseridas, self.atualizadas, self.rpcs, self._t, self._upd = erro, [], [], [], None, None

    def table(self, nome):
        self._t, self._upd = nome, None
        return self

    def select(self, *_):
        return self

    def in_(self, *_):
        return self

    def insert(self, linha):
        if self.erro:
            raise self.erro
        self.inseridas.append(linha)
        return self

    def update(self, campos):
        self._upd = campos
        return self

    def eq(self, _c, ref):
        self.atualizadas.append((ref, self._upd))
        return self

    def rpc(self, nome, args):
        self.rpcs.append(nome)
        return self

    def execute(self):
        if self._t == "oportunidades":
            return type("R", (), {"data": [{"oportunidade_ref": "VEN_1", "responsavel": "Outra Teste"}]})()
        return type("R", (), {"data": [{"visita_ref_ego": "VF_1", "oportunidade_ref": "VEN_1", "visita_observacoes": None}] if self._t == "visitas" else []})()


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(va.ego_api, "oportunidades_ativas", lambda: [{"id": 1, "name": "VEN_1"}])
    monkeypatch.setattr(va, "da_api", lambda ids: [_v("VF_1"), _v("VF_2")])
    monkeypatch.setattr(va.ego_api, "todos_os_imoveis", lambda: [{"id": 10, "reference": "FH0001"}])
    monkeypatch.setattr(va.ego_api, "utilizadores", lambda: {3: "Consultora Teste"})


def test_dry_run_e_interruptor_vazio_so_contam(api, monkeypatch):
    monkeypatch.setattr(va.settings, "visitas_api_ego", "")
    b = _BD()
    r = va.sincronizar(b, dry=False)
    assert r["novas"] == 1 and r["a_completar"] == 1 and r["ligado"] is False
    assert b.inseridas == [] and b.atualizadas == [], "sem interruptor não escreve, mesmo com dry=False"
    monkeypatch.setattr(va.settings, "visitas_api_ego", "1")
    assert va.sincronizar(b, dry=True)["ligado"] is False and b.inseridas == []


def test_grava_so_com_interruptor_e_dry_desligado(api, monkeypatch):
    monkeypatch.setattr(va.settings, "visitas_api_ego", "1")
    b = _BD()
    r = va.sincronizar(b, dry=False)
    assert r["inseridas"] == 1 and r["completadas"] == 1 and r["erros"] == 0
    assert b.inseridas[0]["visita_ref_ego"] == "VF_2" and b.atualizadas[0][0] == "VF_1"
    assert b.rpcs == ["propagar_contacto_id"], "o contacto herda-se por RPC, nunca por escrita direta"


def test_chave_duplicada_nao_e_erro_e_outro_codigo_conta(api, monkeypatch):
    monkeypatch.setattr(va.settings, "visitas_api_ego", "1")

    class _Dup(Exception):
        code = "23505"

    class _Outro(Exception):
        code = "42501"

    assert va.sincronizar(_BD(erro=_Dup()), dry=False)["erros"] == 0, "o relatório chegou entretanto"
    assert va.sincronizar(_BD(erro=_Outro()), dry=False)["erros"] == 1
