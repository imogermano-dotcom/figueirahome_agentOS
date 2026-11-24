"""Pedido #20 (21/11): a escalada avisa as consultoras das oportunidades ativas do telefone (`docs/fases/escalar-aviso-imediato-plano.md`).

Telefones de teste: `912345678`. Sem rede: Supabase e `notificar` são duplos.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.tools as tools  # noqa: E402
from app import notificacoes  # noqa: E402

OPS = [{"oportunidade_ref": "CAP_1", "imovel_ref": "APA_1", "responsavel": "Ana Teste"},
       {"oportunidade_ref": "CAP_2", "imovel_ref": "APA_2", "responsavel": "Bia Teste"},
       {"oportunidade_ref": "CAP_3", "imovel_ref": "APA_3", "responsavel": "Ana Teste"}]
PERFIS = [{"ego_responsavel": "Ana Teste", "email": "ana@example.com"}, {"ego_responsavel": "Bia Teste", "email": "bia@example.com"}]
CONTEXTO = {"canal": "whatsapp", "telefone": "912345678", "agente": "a1_vendedor", "conversa_id": "conv-1"}


class _BD:
    """`oportunidades` e `profiles` devolvem as linhas dadas; guarda os filtros pedidos."""

    def __init__(self, ops=(), perfis=(), rebenta=False):
        self.ops, self.perfis, self.rebenta, self.filtros, self._t = list(ops), list(perfis), rebenta, [], None

    def table(self, nome):
        self._t = nome
        return self

    def __getattr__(self, nome):
        def _filtro(*a, **k):
            self.filtros.append((nome, a))
            return self
        return self if nome == "not_" else _filtro

    def execute(self):
        if self.rebenta:
            raise RuntimeError("bd em baixo")
        return type("R", (), {"data": self.ops if self._t == "oportunidades" else self.perfis})()


def _bd(monkeypatch, **kw):
    bd = _BD(**kw)
    monkeypatch.setattr("app.db.supabase_client.get_supabase", lambda: bd)
    return bd


def test_telefone_liga_as_oportunidades_ativas_e_as_consultoras(monkeypatch):
    bd = _bd(monkeypatch, ops=OPS, perfis=PERFIS)
    r = notificacoes.consultoras_do_telefone("+351912345678")
    assert [o["oportunidade_ref"] for o in r["ops"]] == ["CAP_1", "CAP_2", "CAP_3"]
    assert r["nomes"] == ["Ana Teste", "Bia Teste"] and r["emails"] == ["ana@example.com", "bia@example.com"]
    assert ("eq", ("oportunidade_estado", "Ativa")) in bd.filtros and ("eq", ("apagada_no_ego", False)) in bd.filtros
    assert ("ilike", ("cliente_telefone", "%912345678%")) in bd.filtros, "só os 9 últimos dígitos: o eGO guarda de várias formas"


@pytest.mark.parametrize("telefone", [None, "", "1234"])
def test_telefone_sem_digitos_suficientes_nao_consulta(monkeypatch, telefone):
    monkeypatch.setattr("app.db.supabase_client.get_supabase", lambda: pytest.fail("não devia consultar"))
    assert notificacoes.consultoras_do_telefone(telefone) == {"ops": [], "nomes": [], "emails": [], "cliente_nome": None}


def test_responsavel_sem_perfil_fica_sem_email_e_a_bd_em_baixo_nao_levanta(monkeypatch):
    _bd(monkeypatch, ops=OPS[:1], perfis=[])
    r = notificacoes.consultoras_do_telefone("912345678")
    assert r["nomes"] == ["Ana Teste"] and r["emails"] == []
    _bd(monkeypatch, rebenta=True)
    assert notificacoes.consultoras_do_telefone("912345678") == {"ops": [], "nomes": [], "emails": [], "cliente_nome": None}


def test_texto_das_consultoras():
    assert notificacoes.texto_das_consultoras({"ops": []}) is None
    t = notificacoes.texto_das_consultoras({"ops": OPS[:2]})
    assert "CAP_1 (imóvel APA_1) — Ana Teste" in t and "CAP_2 (imóvel APA_2) — Bia Teste" in t


@pytest.fixture
def escalar(monkeypatch):
    registo = {"avisos": [], "tarefas": []}
    monkeypatch.setattr(tools, "_inserir_tarefa", registo["tarefas"].append)
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: False)
    monkeypatch.setattr(tools, "_angariador_do_imovel", lambda ref: "Carla Teste" if ref == "FH0001" else None)
    monkeypatch.setattr(tools, "notificar", lambda assunto, corpo, imovel_ref=None, para_extra=None:
                        registo["avisos"].append((assunto, corpo, imovel_ref, para_extra)))

    async def _sem_cliente(**kw):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)

    def chamar(ligacao, **extra):
        monkeypatch.setattr(tools, "consultoras_do_telefone", lambda tel: ligacao)
        inputs = {"telefone": "912345678", "motivo": "mensagem para a equipa",
                  "resumo": "Amanhã pelas 18:30 poderá visitar o apartamento", **extra}
        return asyncio.run(tools._escalar_para_humano(inputs, CONTEXTO))

    return chamar, registo


LIGACAO = {"ops": OPS, "nomes": ["Ana Teste", "Bia Teste"], "emails": ["ana@example.com", "bia@example.com"]}
SEM = {"ops": [], "nomes": [], "emails": []}


def test_escalada_sem_imovel_avisa_as_consultoras_das_oportunidades_do_telefone(escalar):
    chamar, registo = escalar
    chamar(LIGACAO)
    (assunto, corpo, imovel, para_extra), = registo["avisos"]
    assert para_extra == ["ana@example.com", "bia@example.com"] and imovel is None
    assert "Amanhã pelas 18:30" in corpo and "912345678" in corpo, "a mensagem tal e qual e o telefone"
    assert "CAP_1 (imóvel APA_1) — Ana Teste" in corpo and "CAP_2" in corpo
    assert "Conversa: conv-1" in corpo and "Matilde" in corpo
    (tarefa,) = registo["tarefas"]
    assert tarefa["responsavel"] == "Ana Teste", "sem imóvel, a 1.ª consultora das oportunidades"


def test_com_imovel_o_responsavel_da_tarefa_continua_a_ser_o_do_imovel(escalar):
    chamar, registo = escalar
    chamar(LIGACAO, imovel_ref="FH0001")
    assert registo["tarefas"][0]["responsavel"] == "Carla Teste"
    assert registo["avisos"][0][2] == "FH0001" and registo["avisos"][0][3] == ["ana@example.com", "bia@example.com"]


def test_sem_oportunidades_o_aviso_vai_so_ao_diretor_como_antes(escalar):
    chamar, registo = escalar
    chamar(SEM)
    (_, corpo, _, para_extra), = registo["avisos"]
    assert para_extra == [] and "Oportunidades ativas" not in corpo
    assert registo["tarefas"][0].get("responsavel") is None


def test_atualizacao_da_escalada_tambem_avisa_as_consultoras(escalar, monkeypatch):
    chamar, registo = escalar
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: True)
    monkeypatch.setattr(tools, "_atualizar_escalada", lambda *a: True)
    chamar(LIGACAO, resumo="Afinal pode ser às 19:00")
    (assunto, corpo, _, para_extra), = registo["avisos"]
    assert "Atualização da escalada" in assunto and "19:00" in corpo and "CAP_1" in corpo
    assert para_extra == ["ana@example.com", "bia@example.com"]
    assert registo["tarefas"] == []


def test_responsavel_principal_prefere_a_op_citada_e_depois_a_maioria():
    from app.notificacoes import responsavel_principal

    ligacao = {"ops": [{"oportunidade_ref": "CAP_1", "imovel_ref": "APA_1", "responsavel": "Ana"},
                       {"oportunidade_ref": "CAP_2", "imovel_ref": "APA_2", "responsavel": "Rita"},
                       {"oportunidade_ref": "CAP_3", "imovel_ref": "APA_3", "responsavel": "Rita"}]}
    assert responsavel_principal(ligacao, "Sobre a visita à CAP_1 amanhã") == "Ana"  # a OP que a mensagem cita ganha
    assert responsavel_principal(ligacao, "Sobre o imóvel apa_1") == "Ana"
    assert responsavel_principal(ligacao, "Amanhã às 18h30 posso visitar?") == "Rita"  # senão, quem tem mais oportunidades
    assert responsavel_principal({"ops": [{"oportunidade_ref": "CAP_1", "responsavel": "Ana"}, {"oportunidade_ref": "CAP_2", "responsavel": "Rita"}]}) == "Ana"  # empate: a primeira
    assert responsavel_principal({"ops": []}) is None and responsavel_principal({"ops": [{"oportunidade_ref": "CAP_1", "responsavel": None}]}) is None
