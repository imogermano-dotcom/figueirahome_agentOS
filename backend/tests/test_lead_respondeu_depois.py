"""Lead já no eGO que responde depois de criada: aviso à consultora (`docs/fases/lead-no-ego-respondeu-depois-plano.md`).

Telefones de teste: `912345678`. Sem rede. Corre com `pytest backend/tests/`.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.config import settings  # noqa: E402
from tests.test_leads_para_ego import AGORA, ISO, _linha  # noqa: E402

MENSAGENS = [{"role": "assistant", "content": "Olá! Posso ajudar?"},
             {"role": "user", "content": "Podes enviar fotos? Têm garagem?"},
             {"role": "assistant", "content": "Sim, tem garagem. Quer visitar?"},
             {"role": "user", "content": "Sim, estou interessada"}]


class _BD:
    """`contactos` devolve `linhas`; `agente_tarefas` devolve `tarefas` e regista os inserts."""

    def __init__(self, linhas, tarefas=()):
        self.linhas, self.tarefas, self.inserts, self._t, self._ins = linhas, list(tarefas), [], None, None

    def table(self, nome):
        self._t, self._ins = nome, None
        return self

    def __getattr__(self, nome):
        return self if nome == "not_" else (lambda *a, **k: self)

    def insert(self, valores):
        self._ins = valores
        return self

    def execute(self):
        if self._ins is not None:
            self.inserts.append(self._ins)
            return type("R", (), {"data": [self._ins]})()
        dados = {"contactos": self.linhas, "agente_tarefas": self.tarefas}.get(self._t, [])
        return type("R", (), {"data": dados})()


def _lead(**kw):
    """Criada às 02:10 «sem resposta», respondeu às 10:19; hoje são as 12:00 (entrada de há 2 dias)."""
    return _linha(meta_created_at=ISO(48), template_enviado_em=ISO(48), ego_lead_em=ISO(10), ego_lead_id=60977396,
                  respondeu_em=ISO(2), **kw)


def _usa(monkeypatch, bd, atividade_h=5, textos=("Sim, estou interessada",)):
    monkeypatch.setattr(settings, "lead_respondeu_ego", "1")
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")
    monkeypatch.setattr(lp, "get_supabase", lambda: bd)
    monkeypatch.setattr(lp, "_conversa_do", lambda tel, desde=None: (AGORA - timedelta(hours=atividade_h), list(textos)))
    monkeypatch.setattr(lp, "_mensagens_do", lambda tel, desde=None: list(MENSAGENS))
    avisos = []
    monkeypatch.setattr(lp, "notificar", lambda assunto, corpo, **k: avisos.append((assunto, corpo, k)))
    return avisos


def test_responde_depois_da_lead_e_a_conversa_assenta_avisa_a_consultora_uma_vez(monkeypatch):
    bd = _BD([_lead()])
    avisos = _usa(monkeypatch, bd)
    assert lp.avisar_respondeu_depois(AGORA) == 1
    (assunto, corpo, k), = avisos
    assert "respondeu à Matilde" in assunto and k["imovel_ref"] == "FH0001"
    assert "60977396" in corpo and "sem resposta" in corpo and "Podes enviar fotos" in corpo
    assert "912345678" in corpo, "o telefone vai à consultora no email, nunca para o repo"
    (tarefa,) = bd.inserts
    assert tarefa["tipo"] == "lead_ego_aviso" and tarefa["estado"] == "concluida"
    # a volta seguinte vê o aviso gravado e não repete
    bd2 = _BD([_lead()], tarefas=[{"id": "t1"}])
    avisos2 = _usa(monkeypatch, bd2)
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos2 and not bd2.inserts


def test_conversa_ainda_a_decorrer_espera(monkeypatch):
    avisos = _usa(monkeypatch, _BD([_lead()]), atividade_h=1)
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


@pytest.mark.parametrize("extra", [{"respondeu_em": None}, {"respondeu_em": ISO(11)}, {"nao_contactar_em": ISO(1)}])
def test_sem_resposta_depois_da_marca_nao_avisa(monkeypatch, extra):
    # `respondeu_em` anterior à marca (ISO(11) < ISO(10)) conta-se no OBS; `nao_contactar_em` é recusa
    linhas = [_lead() | extra] if "nao_contactar_em" not in extra else []  # o filtro `is_null` é do servidor: o duplo não o aplica
    avisos = _usa(monkeypatch, _BD(linhas))
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


def test_marca_de_entrada_anterior_nao_conta(monkeypatch):
    avisos = _usa(monkeypatch, _BD([_lead() | {"ego_lead_em": ISO(24 * 20)}]))
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


@pytest.mark.parametrize("textos", [("Obrigado, até breve",), ("Sim", "Já não estou interessado")])
def test_despedida_ou_recusa_nao_avisa(monkeypatch, textos):
    avisos = _usa(monkeypatch, _BD([_lead()]), textos=textos)
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


def test_desligado_sem_o_segredo(monkeypatch):
    avisos = _usa(monkeypatch, _BD([_lead()]))
    monkeypatch.setattr(settings, "lead_respondeu_ego", "")
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


def test_piloto_so_avisa_os_numeros_da_lista(monkeypatch):
    avisos = _usa(monkeypatch, _BD([_lead()]))
    monkeypatch.setattr(settings, "lead_respondeu_ego", "999")
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


def test_falha_a_gravar_o_aviso_nao_envia_nem_levanta(monkeypatch):
    bd = _BD([_lead()])
    avisos = _usa(monkeypatch, bd)
    bd.insert = lambda valores: (_ for _ in ()).throw(RuntimeError("bd em baixo"))
    assert lp.avisar_respondeu_depois(AGORA) == 0 and not avisos


def test_falha_do_email_nao_levanta(monkeypatch):
    bd = _BD([_lead()])
    _usa(monkeypatch, bd)
    monkeypatch.setattr(lp, "notificar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp")))
    assert lp.avisar_respondeu_depois(AGORA) == 0


def test_a_volta_do_cron_avisa_mesmo_sem_candidatas_a_criar(monkeypatch):
    bd = _BD([_lead()])
    _usa(monkeypatch, bd)
    monkeypatch.setattr(lp, "preencher_responsavel_meta", lambda: {})
    monkeypatch.setattr(lp, "_candidatas", lambda agora: [])
    monkeypatch.setattr(lp, "_candidatas_interesse", lambda agora: [])
    monkeypatch.setattr(lp, "_candidatas_paradas", lambda agora: [])
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")
    assert lp.processar(AGORA)["respondeu_depois"] == 1
