"""A lead que responde depois de criada: ver o estado no eGO e criar lead nova se já não está na caixa
(`docs/fases/lead-responde-depois-estado-plano.md`).

Telefones de teste: `912345678`. Sem rede: Supabase, eGO e `notificar` são duplos.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.agents.broker import guards  # noqa: E402
from app.config import settings  # noqa: E402
from tests.test_leads_para_ego import AGORA, ISO, _linha  # noqa: E402

PRE = "Olá! Preenchi o teu formulário e gostaria de saber mais sobre o teu negócio."


def _msgs(horas_depois=(8,), extra=()):
    """Mensagens da conversa: a pré-preenchida (antes da lead) e as da pessoa `horas_depois` horas antes de AGORA."""
    m = [{"role": "user", "content": PRE, "timestamp": ISO(30)}, {"role": "assistant", "content": "Olá!", "timestamp": ISO(30)}]
    for h in horas_depois:
        m += [{"role": "user", "content": "Sim, estou interessada. Têm garagem?", "timestamp": ISO(h)},
              {"role": "assistant", "content": "Sim, tem garagem.", "timestamp": ISO(h)}]
    return m + list(extra)


class _BD:
    """`contactos` devolve `linhas`; `agente_tarefas` as `tarefas` (dedup); `agente_sync_log` os `logs`; regista inserts e updates."""

    def __init__(self, linhas, tarefas=(), logs=(), conversa=None, atividade_h=6):
        self.linhas, self.tarefas, self.logs = linhas, list(tarefas), list(logs)
        self.conversa = _msgs() if conversa is None else conversa
        self.atividade_h = atividade_h
        self.inserts, self.updates, self._t, self._ins, self._upd = [], [], None, None, None

    def table(self, nome):
        self._t, self._ins, self._upd = nome, None, None
        return self

    def __getattr__(self, nome):
        return self if nome == "not_" else (lambda *a, **k: self)

    def insert(self, valores):
        self._ins = valores
        return self

    def update(self, valores):
        self._upd = valores
        return self

    def eq(self, _, valor):
        if self._upd is not None and self._t == "contactos":
            self.updates.append((valor, self._upd))
        return self

    def execute(self):
        if self._ins is not None:
            self.inserts.append((self._t, self._ins))
            return type("R", (), {"data": [self._ins]})()
        if self._upd is not None:
            return type("R", (), {"data": []})()
        dados = {"contactos": self.linhas, "agente_tarefas": self.tarefas, "agente_sync_log": self.logs,
                 "agente_conversas": [{"atualizado_em": ISO(self.atividade_h), "mensagens": self.conversa}]}.get(self._t, [])
        return type("R", (), {"data": dados})()


def _lead(**kw):
    """Criada às 02:10 (há 10 h), entrada há 2 dias; a pessoa escreveu depois (há 8 h) e a conversa parou há 6 h."""
    return _linha(meta_created_at=ISO(48), template_enviado_em=ISO(48), ego_lead_em=ISO(10), ego_lead_id=60977396,
                  respondeu_em=ISO(30), **kw)


def _usa(monkeypatch, bd, caixa=(), ativacao=None, criar=None, oportunidade="VEN_1"):
    monkeypatch.setattr(settings, "lead_respondeu_ego", "1")
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")
    monkeypatch.setattr(settings, "lead_nova_depois_desde", ativacao or "")
    monkeypatch.setattr(lp, "get_supabase", lambda: bd)
    monkeypatch.setattr(lp.ego_api, "leads_abertas", lambda: list(caixa))
    monkeypatch.setattr(lp, "_oportunidade_da_lead", lambda l: oportunidade)
    monkeypatch.setattr(lp, "_imovel_da_entrada", lambda l: l)
    criadas = []
    monkeypatch.setattr(lp, "_criar_lead", criar or (lambda linha, tel, **k: criadas.append(linha) or 777))
    avisos = []
    monkeypatch.setattr(lp, "notificar", lambda assunto, corpo, **k: avisos.append((assunto, corpo, k)))
    return criadas, avisos


ATIVA = ISO(20)  # a lead nova só vale para conversa posterior a isto (há 20 h)


def test_lead_ainda_na_caixa_so_manda_email_e_nao_cria(monkeypatch):
    bd = _BD([_lead()])
    criadas, avisos = _usa(monkeypatch, bd, caixa=[{"id": 60977396, "phone": "+351912345678"}], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA) == {"avisadas": 1, "criadas": 0, "erros": 0}
    (assunto, corpo, k), = avisos
    assert "continua na caixa" in corpo and "Têm garagem" in corpo and k["imovel_ref"] == "FH0001"
    assert PRE not in corpo, "a mensagem pré-preenchida nunca vai para a consultora"
    assert not criadas
    (tabela, tarefa), = bd.inserts
    assert tabela == "agente_tarefas" and tarefa["tipo"] == "lead_ego_aviso" and "respondeu depois" in tarefa["descricao"]


def test_lead_fora_da_caixa_cria_lead_nova_marca_e_avisa_com_a_oportunidade(monkeypatch):
    bd = _BD([_lead()])
    criadas, avisos = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA) == {"avisadas": 0, "criadas": 1, "erros": 0}
    (nova,) = criadas
    assert nova["voltou_a_responder"] and nova["oportunidade_anterior"] == "VEN_1"
    assert "Têm garagem" in nova["respostas_da_pessoa"] and PRE not in nova["respostas_da_pessoa"]
    (id_, marca), = bd.updates
    assert id_ == "c1" and marca["ego_lead_id"] == 777 and marca["ego_lead_em"] == AGORA.isoformat()
    (_, corpo, _), = avisos
    assert "oportunidade VEN_1" in corpo and "criou-se uma lead nova" in corpo
    log = [v for t, v in bd.inserts if t == "agente_sync_log"]
    assert log and log[0]["resumo"]["via"] == "respondeu_depois" and log[0]["resumo"]["contactos"] == ["c1"]


def test_obs_da_lead_nova():
    obs = lp.observacao_da_lead(_lead() | {"voltou_a_responder": True, "oportunidade_anterior": "VEN_1",
                                          "respostas_da_pessoa": "Pediu: Têm garagem?"}, com_imovel=True, ja_conhecido=True)
    assert "voltou a responder à Matilde depois de a lead anterior ser tratada (oportunidade VEN_1)" in obs
    assert "Respostas da pessoa: Pediu: Têm garagem?" in obs and "sem resposta" not in obs and "interesse real" not in obs


def test_sem_data_de_ativacao_nunca_cria_so_o_email_da_caixa(monkeypatch):
    bd = _BD([_lead()])
    criadas, avisos = _usa(monkeypatch, bd, caixa=[], ativacao=None)
    assert lp.tratar_respondeu_depois(AGORA) == {"avisadas": 0, "criadas": 0, "erros": 0}
    assert not criadas and not avisos and not bd.inserts


def test_conversa_anterior_a_ativacao_nao_cria(monkeypatch):
    """O caso HD (23/11): a conversa toda é anterior ao deploy, por isso não se cria nada retroativamente."""
    bd = _BD([_lead()])
    criadas, avisos = _usa(monkeypatch, bd, caixa=[], ativacao=ISO(1))
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas


def test_no_maximo_uma_lead_nova_por_dia(monkeypatch):
    bd = _BD([_lead()], logs=[{"resumo": {"via": "respondeu_depois", "contactos": ["c1"]}}])
    criadas, _ = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas
    bd2 = _BD([_lead()], logs=[{"resumo": {"via": "cron", "contactos": ["c1"]}}, {"resumo": {"via": "respondeu_depois", "contactos": ["outro"]}}])
    criadas2, _ = _usa(monkeypatch, bd2, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 1 and len(criadas2) == 1


def test_sem_consultora_nao_cria_nem_marca_e_conta_erro(monkeypatch):
    def _sem(linha, tel, **k):
        raise lp.SemConsultora("imóvel sem responsável")

    bd = _BD([_lead()])
    criadas, avisos = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA, criar=_sem)
    assert lp.tratar_respondeu_depois(AGORA) == {"avisadas": 0, "criadas": 0, "erros": 1}
    assert not bd.updates and not avisos


def test_sem_email_nao_cria(monkeypatch):
    bd = _BD([_lead(email="")])
    criadas, _ = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA) == {"avisadas": 0, "criadas": 0, "erros": 1} and not criadas


def test_falha_da_api_do_eGO_nao_cria_nada(monkeypatch):
    bd = _BD([_lead()])
    criadas, avisos = _usa(monkeypatch, bd, ativacao=ATIVA)

    def _rebenta():
        raise RuntimeError("eGO em baixo")

    monkeypatch.setattr(lp.ego_api, "leads_abertas", _rebenta)
    assert lp.tratar_respondeu_depois(AGORA)["erros"] == 1 and not criadas and not avisos and not bd.updates


def test_conversa_ainda_a_decorrer_espera(monkeypatch):
    bd = _BD([_lead()], atividade_h=1)
    criadas, avisos = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA) == {"avisadas": 0, "criadas": 0, "erros": 0} and not criadas and not avisos


def test_so_a_mensagem_pre_preenchida_ou_nada_depois_da_lead_nao_conta(monkeypatch):
    bd = _BD([_lead()], conversa=[{"role": "user", "content": PRE, "timestamp": ISO(5)}])  # pré-preenchida, mesmo depois da marca
    criadas, avisos = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas
    bd2 = _BD([_lead()], conversa=_msgs(horas_depois=(12,)))  # a pessoa só escreveu antes da lead (há 12 h > há 10 h)
    _usa(monkeypatch, bd2, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0


def test_mensagens_sem_hora_nao_contam(monkeypatch):
    bd = _BD([_lead()], conversa=[{"role": "user", "content": "Têm garagem?"}])
    criadas, _ = _usa(monkeypatch, bd, caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas


@pytest.mark.parametrize("textos", [["Obrigado, até breve"], ["Sim", "Já não estou interessado"],
                                    ["Muito obrigada pela atenção mas está um pouco longe do meu alcance. Pena, parecia o ideal. Grata."]])
def test_despedida_ou_recusa_depois_da_lead_nao_trata(monkeypatch, textos):
    conversa = [{"role": "user", "content": t, "timestamp": ISO(8)} for t in textos]
    criadas, avisos = _usa(monkeypatch, _BD([_lead()], conversa=conversa), caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas and not avisos


def test_aviso_da_qualificacao_nao_bloqueia_mas_o_da_porta_nao_repete(monkeypatch):
    """O `lead_ego_aviso` da qualificação tem outra descrição: a porta atua. O da própria porta ('respondeu depois') não repete."""
    # o duplo devolve as `tarefas` a qualquer pergunta; a descrição distingue-se no filtro `ilike` real, aqui só se vê o efeito
    bd = _BD([_lead()], tarefas=[{"id": "t1"}])
    criadas, avisos = _usa(monkeypatch, bd, caixa=[{"id": 60977396}], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["avisadas"] == 0 and not avisos, "já tratada nesta lead: não repete"


def test_marca_de_entrada_anterior_nao_conta(monkeypatch):
    criadas, avisos = _usa(monkeypatch, _BD([_lead() | {"ego_lead_em": ISO(24 * 60)}]), caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas


def test_desligado_sem_o_segredo_e_piloto(monkeypatch):
    criadas, avisos = _usa(monkeypatch, _BD([_lead()]), caixa=[], ativacao=ATIVA)
    monkeypatch.setattr(settings, "lead_respondeu_ego", "")
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0
    monkeypatch.setattr(settings, "lead_respondeu_ego", "999")
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0


def test_a_volta_do_cron_trata_mesmo_sem_candidatas_a_criar(monkeypatch):
    bd = _BD([_lead()])
    _usa(monkeypatch, bd, caixa=[{"id": 60977396}], ativacao=ATIVA)
    monkeypatch.setattr(lp, "preencher_responsavel_meta", lambda: {})
    monkeypatch.setattr(lp, "_candidatas", lambda agora: [])
    monkeypatch.setattr(lp, "_candidatas_interesse", lambda agora: [])
    monkeypatch.setattr(lp, "_candidatas_paradas", lambda agora: [])
    assert lp.processar(AGORA)["respondeu_depois"]["avisadas"] == 1


# ── a mensagem pré-preenchida do formulário não é interesse ─────────────────────────────────────

def test_mensagem_pre_preenchida_nao_e_pedido_de_informacao():
    assert guards.e_mensagem_pre_preenchida(PRE)
    assert not guards.e_pedido_de_informacao(PRE), "«gostaria de saber mais» era apanhado e marcava interesse real em 6 s"
    assert guards.e_pedido_de_informacao("Gostaria de saber mais sobre o preço")
    assert not guards.e_mensagem_pre_preenchida("Preenchi o formulário ontem")


def test_pre_preenchida_fora_do_resumo_e_das_respostas():
    msgs = [{"role": "user", "content": PRE}, {"role": "assistant", "content": "Olá! Que orçamento tem?"},
            {"role": "user", "content": "Até 250 mil"}]
    r = lp.respostas_da_pessoa(msgs)
    assert r.startswith("Pediu: Até 250 mil") and "Preenchi" not in r
    assert lp.resumo_da_conversa([PRE, "Até 250 mil"]) == "Até 250 mil"


def test_so_leads_nossas_tem_id_do_eGO(monkeypatch):
    """DJ (23/11): a marca era «já existia» (oportunidade ativa), sem lead nossa: não é lead a recriar."""
    criadas, avisos = _usa(monkeypatch, _BD([_lead() | {"ego_lead_id": None}]), caixa=[], ativacao=ATIVA)
    assert lp.tratar_respondeu_depois(AGORA)["criadas"] == 0 and not criadas


@pytest.mark.parametrize("texto,fora", [("está um pouco longe do meu alcance", True), ("Fora do meu orçamento", True),
                                         ("Acho caro", False), ("é muito caro para mim", True), ("Qual o preço?", False),
                                         ("Tenho um orçamento de 250 mil", False)])
def test_fora_do_alcance(texto, fora):
    assert guards.e_fora_do_alcance(texto) is fora
