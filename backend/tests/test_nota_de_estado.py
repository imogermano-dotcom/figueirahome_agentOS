"""Nota de estado depois de escalar (`docs/fases/nota-de-estado-escalada-plano.md`, 08/10)."""

import asyncio
from types import SimpleNamespace

from app.agents.broker import guards
from app.agents.broker.engine import _ERRO, _RESPOSTA_ESCALADA, _montar_system_prompt, _sem_erro_apos_registo


def _fake(monkeypatch, linhas=None, erro=False):
    class _Q:
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self):
            if erro:
                raise RuntimeError("base em baixo")
            return SimpleNamespace(data=linhas or [])

    monkeypatch.setattr(guards, "get_supabase", lambda: SimpleNamespace(table=lambda n: _Q()))


def test_motivos_distintos_e_ordenados(monkeypatch):
    _fake(monkeypatch, [{"motivo": "venda"}, {"motivo": "avaliação"}, {"motivo": "venda"}, {"motivo": None}])
    assert asyncio.run(guards.motivos_escalados("c1")) == ["avaliação", "venda"]


def test_sem_conversa_ou_sem_tarefas_devolve_vazio(monkeypatch):
    _fake(monkeypatch)
    assert asyncio.run(guards.motivos_escalados(None)) == []
    assert asyncio.run(guards.motivos_escalados("c1")) == []


def test_erro_da_base_falha_aberto(monkeypatch):
    _fake(monkeypatch, erro=True)
    assert asyncio.run(guards.motivos_escalados("c1")) == []


def test_prompt_sem_escalada_nao_muda():
    spec = {"prompt": "base"}
    assert _montar_system_prompt(spec, "", "", "whatsapp") == _montar_system_prompt(spec, "", "", "whatsapp", [])
    assert "Estado desta conversa" not in _montar_system_prompt(spec, "", "", "whatsapp")


def test_prompt_escalado_tem_a_nota_uma_vez_e_e_estavel():
    spec = {"prompt": "base"}
    a = _montar_system_prompt(spec, "", "", "whatsapp", ["entrevista de recrutamento"])
    b = _montar_system_prompt(spec, "", "", "whatsapp", ["entrevista de recrutamento"])
    assert a == b  # cache
    assert a.count("Estado desta conversa") == 1 and "entrevista de recrutamento" in a


def test_fallback_cobre_escalada_de_turnos_anteriores():
    assert _sem_erro_apos_registo(_ERRO, [], escalados=["venda"]) == _RESPOSTA_ESCALADA
    assert _sem_erro_apos_registo(_ERRO, [], [], []) == _ERRO


# ── generalização às tools de registo (estado-da-conversa-e-aviso-unico-plano.md) ──

from app.agents.broker.engine import _RESPOSTA_REGISTADA, _nota_de_estado  # noqa: E402


def _fake_interacoes(monkeypatch, linhas=None, erro=False):
    class _Q:
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self):
            if erro:
                raise RuntimeError("base em baixo")
            return SimpleNamespace(data=linhas or [])

    monkeypatch.setattr(guards, "get_supabase", lambda: SimpleNamespace(table=lambda n: _Q()))


def test_tools_ja_usadas_so_registo_distintas_e_ordenadas(monkeypatch):
    _fake_interacoes(monkeypatch, [
        {"tools_usadas": ["pesquisar_imoveis", "guardar_dados_cliente"]},
        {"tools_usadas": None},
        {"tools_usadas": ["guardar_dados_cliente", "escalar_para_humano", "ficha_imovel"]},
    ])
    assert asyncio.run(guards.tools_ja_usadas("c1")) == ["escalar_para_humano", "guardar_dados_cliente"]


def test_tools_ja_usadas_sem_conversa_ou_com_erro(monkeypatch):
    assert asyncio.run(guards.tools_ja_usadas(None)) == []
    _fake_interacoes(monkeypatch, erro=True)
    assert asyncio.run(guards.tools_ja_usadas("c1")) == []


def test_nota_so_com_guardar_diz_que_os_dados_ja_estao_guardados():
    nota = _nota_de_estado([], ["guardar_dados_cliente"])
    assert "Já guardaste os dados" in nota and "entregue a um humano" not in nota
    assert nota == _nota_de_estado([], ["guardar_dados_cliente"])  # estável (cache)


def test_nota_sem_estado_e_vazia_e_a_pesquisa_nao_conta():
    assert _nota_de_estado([], []) == ""
    assert _nota_de_estado([], ["pesquisar_imoveis"]) == ""


def test_nota_com_escalada_e_guardar_junta_as_duas_sem_repetir_cabecalho():
    nota = _nota_de_estado(["venda"], ["guardar_dados_cliente"])
    assert nota.count("Estado desta conversa") == 1 and "venda" in nota and "Já guardaste" in nota


def test_fallback_so_com_guardar_nao_promete_contacto():
    r = _sem_erro_apos_registo(_ERRO, ["guardar_dados_cliente"])
    assert r == _RESPOSTA_REGISTADA and "contacto" not in r
    assert _sem_erro_apos_registo(_ERRO, [], ["guardar_dados_cliente"]) == _RESPOSTA_REGISTADA
