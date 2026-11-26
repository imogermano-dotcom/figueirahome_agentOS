"""Esqueleto das oportunidades novas do eGO (pedido #28, 26/11, `docs/fases/oportunidades-em-falta-pela-api-plano.md`).

Telefones, emails e nomes de teste: `912345678`, `x@example.com`, `Pessoa Teste`. Sem rede: Supabase e a API são duplos.
"""

import pytest

from app.integrations import ego_oportunidades as eo


def _o(ref="VEN_1", **extra):
    return {
        "name": ref, "id": 61025788, "title": "Pessoa Teste", "email": "x@example.com", "phone": "912345678", "leadStage": 1,
        "createDate": "2026-11-25T18:20:15", "alterDate": "2026-11-26T11:37:26", "realestateReference": "FH0001",
        "masterLeadType": {"id": 2}, "leadTypeId": 4, "assignToSecurityUserId": 7,
        "leadOrigin": {"id": 11, "nameMls": {"PT-PT": "Outros"}}, "leadSubOrigin": {"id": 1, "nameMls": {"PT-PT": "Facebook campanha"}},
        **extra,
    }


def test_esqueleto_leva_so_o_que_a_lista_da_api_da():
    e = eo.esqueleto(_o(), {7: "Consultora Teste"})
    assert e == {
        "oportunidade_ref": "VEN_1", "oportunidade_estado": "Ativa", "tipo_oportunidade": "Venda", "tipo_pedido": "Pedido de Informação",
        "cliente_nome": "Pessoa Teste", "cliente_email": "x@example.com", "cliente_telefone": "912345678",
        "ego_lead_id": 61025788, "url": "https://admin.egorealestate.com/egocore/Leads/61025788",
        "ego_data_criacao": "2026-11-25", "data_criacao_iso": "2026-11-25", "ego_editado_em": "2026-11-26", "imovel_ref": "FH0001",
        "origem": "Outros", "sub_origem": "Facebook campanha", "responsavel": "Consultora Teste",
    }


@pytest.mark.parametrize("extra", [{"leadStage": 2}, {"leadStage": 3}, {"masterLeadType": {"id": 99}}, {"name": None}])
def test_esqueleto_nao_cria_a_fechada_nem_o_tipo_desconhecido(extra):
    """A lista de «ativas» do eGO traz também Ganhas e Perdidas; um tipo novo não se inventa: fica para o relatório."""
    assert eo.esqueleto(_o(**extra), {}) is None


def test_sem_pedido_nem_responsavel_os_campos_ficam_de_fora():
    e = eo.esqueleto(_o(leadTypeId=0, assignToSecurityUserId=999), {7: "Consultora Teste"})
    assert "tipo_pedido" not in e and "responsavel" not in e
    assert eo.esqueleto(_o(leadStage=0), {})["oportunidade_estado"] == "Ativa", "o estado 0 era «Criada»; o scraper também o guarda como Ativa"


class _BD:
    def __init__(self, existem=(), contactos=None, erro_insert=None):
        self.existem, self.contactos, self.erro_insert = set(existem), contactos or {}, erro_insert
        self.inseridas, self.rpcs, self._t, self._ph = [], [], None, None

    def table(self, nome):
        self._t, self._ph = nome, None
        return self

    def select(self, *_):
        return self

    def in_(self, *_):
        return self

    def limit(self, _):
        return self

    def or_(self, filtro):
        self._ph = filtro.split("%")[1]
        return self

    def ilike(self, _col, valor):
        self._ph = valor
        return self

    def insert(self, linha):
        if self.erro_insert:
            raise self.erro_insert
        self.inseridas.append(linha)
        return self

    def rpc(self, nome, args):
        self.rpcs.append((nome, args))
        return self

    def execute(self):
        if self._t == "oportunidades":
            return type("R", (), {"data": [{"oportunidade_ref": r} for r in self.existem]})()
        if self._t == "contactos":
            return type("R", (), {"data": [{"id": i} for i in self.contactos.get(self._ph, [])]})()
        return type("R", (), {"data": []})()


@pytest.fixture
def bd(monkeypatch):
    def montar(**kw):
        b = _BD(**kw)
        monkeypatch.setattr(eo, "get_supabase", lambda: b)
        monkeypatch.setattr(eo.ego_api, "utilizadores", lambda: {7: "Consultora Teste"})
        return b
    return montar


def test_so_conta_quando_o_interruptor_esta_desligado(bd):
    b = bd(existem={"VEN_0"})
    r = eo.criar_em_falta([_o("VEN_0"), _o("VEN_1"), _o("VEN_2", leadStage=3)], gravar=False)
    assert r == {"em_falta": 2, "saltadas": 1, "criaria": 1} and b.inseridas == []


def test_cria_so_as_que_faltam_e_nunca_toca_nas_que_existem(bd):
    b = bd(existem={"VEN_0"})
    r = eo.criar_em_falta([_o("VEN_0"), _o("VEN_1")], gravar=True)
    assert [i["oportunidade_ref"] for i in b.inseridas] == ["VEN_1"] and r["criadas"] == 1 and r["erros"] == 0


def test_chave_duplicada_e_o_relatorio_a_chegar_nao_e_erro(bd):
    class _Dup(Exception):
        code = "23505"

    b = bd(erro_insert=_Dup())
    r = eo.criar_em_falta([_o("VEN_1")], gravar=True)
    assert r["criadas"] == 0 and r["erros"] == 0
    class _Outro(Exception):
        code = "42501"

    b = bd(erro_insert=_Outro())
    assert eo.criar_em_falta([_o("VEN_1")], gravar=True)["erros"] == 1, "um erro a sério conta"


def test_liga_ao_contacto_so_quando_ha_exatamente_um(bd):
    b = bd(contactos={"912345678": ["c1"]})
    r = eo.criar_em_falta([_o("VEN_1")], gravar=True)
    assert r["ligadas"] == 1
    assert b.rpcs == [("set_contacto_oportunidades", {"pares": [{"oportunidade_ref": "VEN_1", "contacto_id": "c1", "contacto_match": "telefone"}]})]
    b = bd(contactos={"912345678": ["c1", "c2"]})
    r = eo.criar_em_falta([_o("VEN_1")], gravar=True)
    assert r["ligadas"] == 0 and b.rpcs == [], "2 contactos: não se adivinha, fica vazio até à fusão"
    b = bd(contactos={"x@example.com": ["c9"]})
    eo.criar_em_falta([_o("VEN_1", phone=None)], gravar=True)
    assert b.rpcs[0][1]["pares"][0]["contacto_match"] == "email", "sem telefone, o email"


def test_respeita_o_maximo_por_volta(bd, monkeypatch):
    b = bd()
    monkeypatch.setattr(eo, "MAX_POR_VOLTA", 2)
    r = eo.criar_em_falta([_o(f"VEN_{i}") for i in range(5)], gravar=True)
    assert r["em_falta"] == 5 and r["criadas"] == 2 and len(b.inseridas) == 2


def test_sem_ativas_nao_consulta_a_base(monkeypatch):
    monkeypatch.setattr(eo, "get_supabase", lambda: pytest.fail("não devia consultar"))
    assert eo.criar_em_falta([], gravar=True) == {"em_falta": 0}


def test_volta_das_notas_cria_as_oportunidades_antes_e_nao_cai_se_falhar(monkeypatch):
    from app.api import oportunidades_sync as sync
    from app.config import settings
    from app.integrations import ego_notas

    chamadas = []
    monkeypatch.setattr(settings, "notas_api_ego", "")
    monkeypatch.setattr(sync.ego_api, "oportunidades_ativas", lambda: [{"name": "VEN_1"}])
    monkeypatch.setattr(ego_notas, "novas", lambda desde="", ativas=None: chamadas.append(("novas", ativas)) or [])
    monkeypatch.setattr(sync.ego_oportunidades, "criar_em_falta", lambda a, g: chamadas.append(("criar", g)) or {"em_falta": 1, "criaria": 1})
    monkeypatch.setattr(settings, "oportunidades_api_ego", "")
    r = sync.reconciliar_notas()
    assert chamadas == [("criar", False), ("novas", [{"name": "VEN_1"}])], "só conta (interruptor vazio) e antes das notas; a lista lê-se uma vez"
    assert r["oportunidades"] == {"em_falta": 1, "criaria": 1}
    monkeypatch.setattr(settings, "oportunidades_api_ego", "1")
    sync.reconciliar_notas()
    assert chamadas[-2] == ("criar", True)

    def _rebenta(a, g):
        raise RuntimeError("503")

    monkeypatch.setattr(sync.ego_oportunidades, "criar_em_falta", _rebenta)
    assert sync.reconciliar_notas()["oportunidades"] == {"erro": True}, "uma falha aqui não pára as notas"
