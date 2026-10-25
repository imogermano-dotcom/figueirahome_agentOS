"""Lead no eGO quando a pessoa responde à Matilde com interesse real (`docs/fases/lead-interesse-real-ego-plano.md`, pedido #17).

O assistente só MARCA o contacto (`guards.marcar_interesse_real`); o cron `leads_para_ego.processar` cria a lead.
Telefones de teste: `912345678`. Sem rede. Corre com `pytest backend/tests/`.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.agents.broker import guards  # noqa: E402
from app.config import settings  # noqa: E402
from tests.test_leads_para_ego import AGORA, ISO, _BD, _linha, _usa  # noqa: E402


# ── o sinal ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("motivo,compra", [
    ("negociação de preço", True), ("proposta de compra", True), ("pedido de visita", True), ("oferta pelo imóvel", True),
    ("entrevista de recrutamento", False), ("angariação", False), ("reclamação", False), ("assunto legal", False),
    ("proposta de angariação", False), ("", False), (None, False),
])
def test_motivo_de_compra(motivo, compra):
    assert guards.motivo_de_compra(motivo) is compra


class _Contactos:
    """Duplo de `contactos` para `marcar_interesse_real`: devolve `linhas` e regista os updates."""

    def __init__(self, linhas, rebenta=False):
        self.linhas, self.updates, self.rebenta, self._upd, self.tocou = linhas, [], rebenta, None, False

    def table(self, nome):
        assert nome == "contactos"
        self.tocou = True
        self._upd = None
        return self

    def __getattr__(self, nome):
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
        if self.rebenta:
            raise RuntimeError("BD em baixo")
        return type("R", (), {"data": self.linhas})()


def _marcar(monkeypatch, bd, ligado=True):
    monkeypatch.setattr(settings, "lead_interesse_ego", "1" if ligado else "")
    monkeypatch.setattr(guards, "get_supabase", lambda: bd)


def test_desligado_nao_toca_na_bd(monkeypatch):
    bd = _Contactos([{"id": "c1"}])
    _marcar(monkeypatch, bd, ligado=False)
    assert guards.marcar_interesse_real("912345678", "visita", "x") is False and not bd.tocou


def test_primeiro_sinal_grava_motivo_e_resumo(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": None, "interesse_real_resumo": None}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("351912345678", "negociação de preço", "Quer negociar o preço.") is True
    (id_, valores), = bd.updates
    assert id_ == "c1" and valores["interesse_real_motivo"] == "negociação de preço"
    assert valores["interesse_real_resumo"] == "Quer negociar o preço." and valores["interesse_real_em"]


def test_segundo_sinal_acrescenta_ao_resumo_sem_mudar_o_primeiro(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": ISO(1), "interesse_real_resumo": "Pediu visita."}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("912345678", "negociação", "Quer negociar.") is True
    (_, valores), = bd.updates
    assert valores == {"interesse_real_resumo": "Pediu visita.\nQuer negociar."}


def test_sinal_repetido_nao_duplica_o_resumo(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": ISO(1), "interesse_real_resumo": "Pediu visita."}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("912345678", "visita", "Pediu visita.") is True and bd.updates == []


def test_sem_contacto_meta_de_comprador_nao_marca(monkeypatch):
    bd = _Contactos([])  # vendedor, recrutamento, sem meta_lead_id ou já com lead: a consulta não devolve nada
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("912345678", "visita", "x") is False and bd.updates == []


def test_sem_telefone_nao_marca(monkeypatch):
    bd = _Contactos([{"id": "c1"}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real(None, "visita", "x") is False and not bd.tocou


def test_erro_da_bd_nao_levanta(monkeypatch):
    _marcar(monkeypatch, _Contactos([{"id": "c1"}], rebenta=True))
    assert guards.marcar_interesse_real("912345678", "visita", "x") is False


def test_resumo_enorme_e_cortado(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": None, "interesse_real_resumo": None}])
    _marcar(monkeypatch, bd)
    guards.marcar_interesse_real("912345678", "visita", "a" * 5000)
    assert len(bd.updates[0][1]["interesse_real_resumo"]) == 1500


# ── as tools que marcam ───────────────────────────────────────────────────

def _tools(monkeypatch):
    import asyncio  # noqa: F401
    import app.agents.broker.tools as tools

    marcas = []
    monkeypatch.setattr(tools, "marcar_interesse_real", lambda tel, motivo, resumo: marcas.append((tel, motivo, resumo)))
    monkeypatch.setattr(tools, "_preco_do_imovel", lambda ref: {"imovel_ref": "FH0001", "venda_preco": 300000, "morada": "Rua X"})
    monkeypatch.setattr(tools, "_inserir_tarefa", lambda d: None)
    monkeypatch.setattr(tools, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_criar_lead_se_preciso", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: False)

    async def _sem_cliente(**kw):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)
    return tools, marcas


CTX = {"canal": "whatsapp", "telefone": "912345678", "agente": "a1_vendedor", "conversa_id": "c-1"}


def test_pedir_visita_marca_interesse_real(monkeypatch):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    asyncio.run(tools._pedir_visita({"imovel_ref": "FH0001", "nome": "Ana", "telefone": "912345678",
                                     "quando": "sábado", "orcamento": 290000}, CTX))
    (tel, motivo, resumo), = marcas
    assert tel == "912345678" and motivo == "visita" and "FH0001" in resumo and "sábado" in resumo


def test_pedir_visita_recusada_pelos_80_por_cento_nao_marca(monkeypatch):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    r = asyncio.run(tools._pedir_visita({"imovel_ref": "FH0001", "nome": "Ana", "telefone": "912345678", "orcamento": 100000}, CTX))
    assert r.startswith("NÃO REGISTADO") and marcas == []


@pytest.mark.parametrize("motivo,marca", [("negociação de preço", True), ("proposta de compra", True),
                                           ("entrevista de recrutamento", False), ("angariação", False), ("reclamação", False)])
def test_escalar_so_marca_motivos_de_compra(monkeypatch, motivo, marca):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    asyncio.run(tools._escalar_para_humano({"motivo": motivo, "resumo": "Quer negociar.", "nome": "Ana",
                                            "telefone": "912345678", "imovel_ref": "FH0001"}, CTX))
    assert bool(marcas) is marca
    if marca:
        assert marcas[0][1] == motivo and marcas[0][2] == "Quer negociar."


def test_escalada_repetida_nao_volta_a_marcar(monkeypatch):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: True)
    monkeypatch.setattr(tools, "_atualizar_escalada", lambda *a: False)
    asyncio.run(tools._escalar_para_humano({"motivo": "negociação de preço", "resumo": "x"}, CTX))
    assert marcas == []


def test_qualificada_marca_com_o_que_o_cliente_disse(monkeypatch):
    marcas = []
    monkeypatch.setattr(guards, "notificar", lambda *a, **k: pytest.fail("não devia mandar email"))
    monkeypatch.setattr(guards, "marcar_interesse_real", lambda tel, motivo, resumo: marcas.append((tel, motivo, resumo)))

    class _BDLead:
        def table(self, _): return self
        def __getattr__(self, n): return (lambda *a, **k: self)
        def execute(self): return type("R", (), {"data": [{"id": "l1", "estado": "contactada", "cliente_id": None,
                                                           "imovel_ref": None, "tipo": "arrendamento", "origem": "whatsapp"}]})()

    guards._promover_lead(_BDLead(), {"id": "cl1", "nome": "Ana", "telefone": "912345678", "email": None,
                                      "tipo_interesse": "arrendamento", "orcamento": 600, "zona_preferida": "Paranhos"})
    assert marcas == [("912345678", "qualificada", "procura arrendamento, orçamento 600, zona Paranhos")]


# ── o texto da lead ───────────────────────────────────────────────────────

def test_observacao_diz_que_respondeu_e_leva_o_resumo():
    o = lp.observacao_da_lead(_linha(interesse_real_em=ISO(1), interesse_real_motivo="visita",
                                     interesse_real_resumo="Pediu\nvisita ao FH0001. Procura arrendamento."), com_imovel=True)
    assert "interesse real (visita)" in o and "Resumo: Pediu visita ao FH0001. Procura arrendamento." in o
    assert "Contactar por telefone ou WhatsApp." in o and "sem resposta" not in o


def test_observacao_corta_o_resumo_a_600():
    o = lp.observacao_da_lead(_linha(interesse_real_em=ISO(1), interesse_real_resumo="palavra " * 200), com_imovel=True)
    assert len(o.split("Resumo: ")[1].split(" Contactar")[0]) <= 600


def test_observacao_sem_interesse_continua_igual():
    assert "sem resposta ao WhatsApp da Matilde" in lp.observacao_da_lead(_linha(), com_imovel=True)


# ── o cron ────────────────────────────────────────────────────────────────

def _interessada(**kw):
    """Já respondeu à Matilde (o cron das 2 h nunca a veria) e foi marcada."""
    return _linha(respondeu_em=ISO(5), interesse_real_em=ISO(1), interesse_real_motivo="visita",
                  interesse_real_resumo="Pediu visita.", **kw)


def _ligado(monkeypatch, ligado=True):
    monkeypatch.setattr(settings, "lead_interesse_ego", "1" if ligado else "")


def test_cron_cria_a_lead_de_quem_respondeu_com_interesse(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    r = lp.processar(AGORA)
    assert (r["criadas"], r["erros"]) == (1, 0)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat(), "ego_lead_id": 555})]
    assert "interesse real (visita)" in corpos[0] and "Pediu visita." in corpos[0]


def test_cron_sem_o_segredo_ignora_quem_respondeu(monkeypatch):
    _ligado(monkeypatch, ligado=False)
    bd = _BD([_interessada()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    r = lp.processar(AGORA)
    assert r["criadas"] == 0 and bd.updates == []


def test_cron_nao_duplica_a_lead_que_ja_esta_na_caixa(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"), leads=[{"phone": "+351912345678"}])
    r = lp.processar(AGORA)
    assert r["ja_existiam"] == 1 and bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat()})]


def test_cron_pessoa_com_oportunidade_ativa_nao_cria(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada()], oportunidade=True)
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["ja_existiam"] == 1


def test_cron_sem_email_fica_por_criar_e_conta_como_erro(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada(email=None)])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    r = lp.processar(AGORA)
    assert r["erros"] == 1 and bd.updates == []


def test_cron_fora_do_horario_espera(monkeypatch):
    from datetime import datetime, timezone
    _ligado(monkeypatch)
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")
    monkeypatch.setattr(lp, "get_supabase", lambda: pytest.fail("não devia tocar na BD"))
    assert lp.processar(datetime(2026, 10, 17, 22, 0, tzinfo=timezone.utc)) == {"ativo": True, "fora_do_horario": True}


def test_cron_contacto_que_entra_pelas_duas_vias_cria_uma_so_vez(monkeypatch):
    """Sem resposta há 3 h e marcada: aparece nas duas consultas e só se cria uma lead."""
    _ligado(monkeypatch)
    bd = _BD([_linha(interesse_real_em=ISO(1), interesse_real_motivo="visita")])
    criadas = []
    _usa(monkeypatch, bd, lambda *a: criadas.append(1) or "555")
    r = lp.processar(AGORA)
    assert r["criadas"] == 1 and len(criadas) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
