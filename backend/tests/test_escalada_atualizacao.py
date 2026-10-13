"""Atualização da escalada e turno vazio com resposta real
(`docs/fases/escalada-atualizacao-e-turno-vazio-plano.md`, 13/10).

Caso real: depois de escalar, "só dá para a semana" ficou sem registo e a candidata foi
avisada de que o responsável "teria isso em conta".
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agents.broker import tools
from app.agents.broker.engine import (
    _INSTRUCAO_RESPOSTA_FINAL, _NOTA_ESCALADA, _com_instrucao_de_resposta,
)

CONTEXTO = {"canal": "whatsapp", "telefone": "912345678", "agente": "a3_recrutamento", "conversa_id": "conv-1"}
MOTIVO = "entrevista de recrutamento"


class _Q:
    def __init__(self, linhas):
        self.linhas, self.filtros, self._upd = linhas, [], None

    def select(self, *a):
        return self

    def eq(self, c, v):
        self.filtros.append((c, v))
        return self

    def limit(self, *a):
        return self

    def update(self, dados):
        self._upd = dados
        return self

    def execute(self):
        escolhidas = [r for r in self.linhas if all(r.get(c) == v for c, v in self.filtros)]
        if self._upd is not None:
            for r in escolhidas:
                r.update(self._upd)
        return SimpleNamespace(data=escolhidas)


@pytest.fixture
def mundo(monkeypatch):
    tarefa = {"id": "t1", "conversa_id": "conv-1", "tipo": "escalar", "motivo": MOTIVO,
              "estado": "pendente", "descricao": "Motivo: x\nResumo inicial."}
    linhas = [tarefa]
    avisos = []
    monkeypatch.setattr(tools, "get_supabase", lambda: SimpleNamespace(table=lambda n: _Q(linhas)))
    monkeypatch.setattr(tools, "notificar", lambda assunto, corpo, imovel_ref=None: avisos.append((assunto, corpo)))
    monkeypatch.setattr(tools, "_inserir_tarefa", lambda d: linhas.append(d))

    async def _sem_cliente(**kw):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)

    def escalar(resumo, motivo=MOTIVO):
        return asyncio.run(tools._escalar_para_humano(
            {"nome": "Ana Luísa", "telefone": "912345678", "motivo": motivo, "resumo": resumo}, CONTEXTO,
        ))

    return tarefa, linhas, avisos, escalar


def test_informacao_nova_e_acrescentada_e_avisa(mundo):
    tarefa, linhas, avisos, escalar = mundo
    resposta = escalar("Só está disponível a partir da próxima semana.")

    assert "Resumo inicial." in tarefa["descricao"]  # acrescenta, não substitui
    assert "Atualização às" in tarefa["descricao"] and "próxima semana" in tarefa["descricao"]
    assert len(linhas) == 1  # nenhuma tarefa nova
    assert len(avisos) == 1 and avisos[0][0].startswith("Atualização da escalada") and "próxima semana" in avisos[0][1]
    assert resposta.startswith("Atualizado")


def test_repeticao_literal_nao_altera_nem_avisa(mundo):
    tarefa, _, avisos, escalar = mundo
    antes = tarefa["descricao"]
    resposta = escalar("Resumo inicial.")
    assert tarefa["descricao"] == antes and avisos == []
    assert "já está registado" in resposta.lower()


def test_atualizacao_repetida_so_conta_uma_vez(mundo):
    tarefa, _, avisos, escalar = mundo
    escalar("Só dá para a semana.")
    escalar("Só dá para a semana.")
    assert tarefa["descricao"].count("Só dá para a semana.") == 1 and len(avisos) == 1


@pytest.mark.parametrize("resumo", ["", "   ", None])
def test_sem_resumo_nao_altera(mundo, resumo):
    tarefa, _, avisos, escalar = mundo
    antes = tarefa["descricao"]
    escalar(resumo)
    assert tarefa["descricao"] == antes and avisos == []


def test_tarefa_concluida_nao_e_reaberta(mundo):
    tarefa, _, avisos, escalar = mundo
    tarefa["estado"] = "concluida"
    antes = tarefa["descricao"]
    resposta = escalar("Informação nova qualquer.")
    assert tarefa["descricao"] == antes and avisos == []
    assert "já está registado" in resposta.lower()


def test_descricao_cheia_nao_acrescenta(mundo):
    tarefa, _, avisos, escalar = mundo
    tarefa["descricao"] = "x" * (tools._MAX_DESCRICAO_TAREFA - 5)
    antes = tarefa["descricao"]
    escalar("Informação nova.")
    assert tarefa["descricao"] == antes and avisos == []


def test_motivo_diferente_continua_a_criar_tarefa_nova(mundo):
    _, linhas, avisos, escalar = mundo
    escalar("Quer vender uma casa.", motivo="venda")
    assert len(linhas) == 2 and linhas[1]["motivo"] == "venda"
    assert avisos and avisos[0][0].startswith("Escalado pelo assistente")


# ── P1: instrução na chamada final ──────────────────────────────────────────

def test_instrucao_vai_a_seguir_aos_tool_result():
    msgs = [
        {"role": "user", "content": "Eu não tenho carta de condução"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "ok"}]},
    ]
    novo = _com_instrucao_de_resposta(msgs)
    assert novo[-1]["content"][0]["type"] == "tool_result"  # os tool_result vêm primeiro
    assert novo[-1]["content"][-1] == {"type": "text", "text": _INSTRUCAO_RESPOSTA_FINAL}
    assert len(msgs[-1]["content"]) == 1  # não altera o original


def test_instrucao_com_ultimo_turno_de_texto_simples():
    novo = _com_instrucao_de_resposta([{"role": "user", "content": "Olá"}])
    assert novo[-1]["content"] == [
        {"type": "text", "text": "Olá"}, {"type": "text", "text": _INSTRUCAO_RESPOSTA_FINAL},
    ]


def test_instrucao_sem_turno_de_utilizador_no_fim_nao_mexe():
    msgs = [{"role": "assistant", "content": "Olá"}]
    assert _com_instrucao_de_resposta(msgs) == msgs and _com_instrucao_de_resposta([]) == []


# ── P3: a nota deixa passar informação nova ────────────────────────────────

def test_a_nota_ja_nao_proibe_a_escalada_com_informacao_nova():
    nota = _NOTA_ESCALADA.format(motivos="venda")
    assert "NOVA" in nota and "Não voltes a chamar escalar_para_humano" not in nota
