"""Nota de estado depois de escalar (`docs/fases/nota-de-estado-escalada-plano.md`, 08/10)."""

import asyncio
from types import SimpleNamespace

from app.agents.broker import guards
from app.agents.broker.engine import _ERRO, _RESPOSTA_ESCALADA, _montar_system_prompt, _sem_erro_apos_escalar


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
    assert _sem_erro_apos_escalar(_ERRO, [], ["venda"]) == _RESPOSTA_ESCALADA
    assert _sem_erro_apos_escalar(_ERRO, [], []) == _ERRO
