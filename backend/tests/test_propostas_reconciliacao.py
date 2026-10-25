"""Reconciliação diária do `estado_proposta` pela API do eGO (pedido #34): aceitar/recusar uma proposta não conta
como edição da oportunidade, e o sync das «últimas 48 h» nunca a relê. Sem rede.

Corre com `pytest backend/tests/` ou `python backend/tests/test_propostas_reconciliacao.py`.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import oportunidades_sync as sync  # noqa: E402
from app.integrations import ego_api  # noqa: E402


def _lista_por_codigo(monkeypatch, por_codigo, total_extra=0):
    def _pedido(metodo, caminho, **kw):
        codigo = kw["json"]["proposalStatusIDList"][0]
        lista = [{"name": r} for r in por_codigo.get(codigo, [])]
        return {"opportunities": lista, "totalRows": len(lista) + total_extra}

    monkeypatch.setattr(ego_api, "_pedido", _pedido)


def test_estados_mapeia_os_tres_codigos(monkeypatch):
    _lista_por_codigo(monkeypatch, {1: ["VEN_1"], 3: ["VEN_2"], 4: ["VEN_3"]})
    assert ego_api.estados_de_proposta() == {"VEN_1": "Em avaliação", "VEN_2": "Aceite", "VEN_3": "Rejeitado"}


def test_com_varias_propostas_manda_a_aceite(monkeypatch):
    _lista_por_codigo(monkeypatch, {3: ["VEN_1"], 4: ["VEN_1", "VEN_2"], 1: ["VEN_2"]})
    assert ego_api.estados_de_proposta() == {"VEN_1": "Aceite", "VEN_2": "Em avaliação"}


def test_pagina_incompleta_levanta(monkeypatch):
    _lista_por_codigo(monkeypatch, {3: ["VEN_1"]}, total_extra=5)
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.estados_de_proposta()


class _Tabela:
    def __init__(self, linhas, escritas):
        self.linhas, self.escritas, self._f, self._upd = linhas, escritas, {}, None

    def select(self, *a):
        return self

    def in_(self, campo, valores):
        self._in = set(valores)
        return self

    def update(self, dados):
        self._upd = dados
        return self

    def eq(self, campo, valor):
        self._f[campo] = valor
        return self

    def execute(self):
        if self._upd is not None:
            self.escritas.append((dict(self._f), self._upd))
            return type("R", (), {"data": []})()
        dados = [{"oportunidade_ref": r, "estado_proposta": e} for r, e in self.linhas.items() if r in self._in]
        return type("R", (), {"data": dados})()


def _supabase(monkeypatch, linhas):
    escritas = []
    monkeypatch.setattr(sync, "get_supabase", lambda: type("S", (), {"table": lambda self, n: _Tabela(linhas, escritas)})())
    return escritas


def test_corrige_so_o_que_diverge(monkeypatch):
    monkeypatch.setattr(ego_api, "estados_de_proposta", lambda: {"VEN_1": "Aceite", "VEN_2": "Em avaliação", "VEN_3": "Rejeitado"})
    escritas = _supabase(monkeypatch, {"VEN_1": "Em avaliação", "VEN_2": "Em avaliação", "VEN_3": None})
    resumo = sync.reconciliar_propostas()
    assert resumo == {"na_api": 3, "corrigidas": ["VEN_1: Em avaliação → Aceite"], "por_ler": 1}
    assert escritas == [({"oportunidade_ref": "VEN_1", "estado_proposta": "Em avaliação"}, {"estado_proposta": "Aceite"})]


def test_sem_divergencias_nao_escreve(monkeypatch):
    monkeypatch.setattr(ego_api, "estados_de_proposta", lambda: {"VEN_1": "Aceite"})
    escritas = _supabase(monkeypatch, {"VEN_1": "Aceite"})
    assert sync.reconciliar_propostas()["corrigidas"] == [] and escritas == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
