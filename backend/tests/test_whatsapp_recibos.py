"""Recibos de entrega -> colunas de `contactos` (`docs/fases/recibos-whatsapp-plano.md`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_whatsapp_recibos.py`.
Telefones de teste: `912345678`. Sem rede: o Supabase é um duplo.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.channels.whatsapp import recibos  # noqa: E402

T0 = 1_760_000_000  # unix
ISO = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).isoformat()  # noqa: E731


def _estado(status, codigo=None, ts=T0, destino="351912345678"):
    e = {"status": status, "recipient_id": destino, "timestamp": str(ts)}
    if codigo is not None:
        e["errors"] = [{"code": codigo, "title": "x"}]
    return e


def test_entregue_e_lida_marcam_entregue():
    for qual in ("delivered", "read"):
        ef = recibos.efeito_do_estado(_estado(qual))
        assert ef["tipo"] == "entregue" and ef["numero"] == "912345678"
        assert ef["quando"] == datetime.fromtimestamp(T0, tz=timezone.utc)


def test_131026_marca_falha_permanente():
    ef = recibos.efeito_do_estado(_estado("failed", 131026))
    assert ef["tipo"] == "falhou" and ef["codigo"] == 131026


@pytest.mark.parametrize("codigo", [131049, 131047, 131030, None])
def test_outras_falhas_nao_marcam_o_numero(codigo):
    assert recibos.efeito_do_estado(_estado("failed", codigo)) is None


def test_sent_nao_muda_nada_e_sem_destino_tambem():
    assert recibos.efeito_do_estado(_estado("sent")) is None
    assert recibos.efeito_do_estado({"status": "delivered"}) is None


def test_evento_sem_timestamp_usa_agora():
    e = _estado("delivered")
    del e["timestamp"]
    assert (datetime.now(timezone.utc) - recibos.efeito_do_estado(e)["quando"]).total_seconds() < 5


def test_texto_do_resumo_so_mostra_os_3_ultimos_digitos():
    txt = recibos.texto_do_resumo([{"numero": "912345678", "codigo": 131026}])
    assert "…678" in txt and "912345678" not in txt and "131026" in txt


class _BD:
    """Duplo mínimo de `contactos`: filtra por `in_`, regista os updates por id."""

    def __init__(self, linhas):
        self.linhas = {l["id"]: dict(l) for l in linhas}
        self._col = self._vals = self._upd = self._id = None

    def table(self, _):
        return self

    def select(self, _):
        self._upd = None
        return self

    def in_(self, col, vals):
        self._col, self._vals = col, vals
        return self

    def update(self, valores):
        self._upd = valores
        return self

    def eq(self, _, valor):
        self._id = valor
        return self

    def execute(self):
        if self._upd is not None:
            self.linhas[self._id].update(self._upd)
            return type("R", (), {"data": []})()
        dados = [l for l in self.linhas.values() if l.get(self._col) in self._vals]
        return type("R", (), {"data": dados})()


def _linha(i, **kw):
    base = {"id": i, "telefone": "912345678", "telemovel": None,
            "whatsapp_entregue_em": None, "whatsapp_falhou_em": None, "whatsapp_erro_codigo": None}
    return base | kw


def _usa(monkeypatch, linhas):
    bd = _BD(linhas)
    monkeypatch.setattr(recibos, "get_supabase", lambda: bd)
    return bd


def test_falha_marca_todas_as_linhas_do_telefone_em_qualquer_formato(monkeypatch):
    bd = _usa(monkeypatch, [_linha(1), _linha(2, telefone="351912345678"), _linha(3, telefone=None, telemovel="+351912345678"),
                            _linha(4, telefone="999999999")])
    recibos.registar(_estado("failed", 131026))
    assert [bd.linhas[i]["whatsapp_erro_codigo"] for i in (1, 2, 3, 4)] == [131026, 131026, 131026, None]


def test_entrega_posterior_limpa_a_falha(monkeypatch):
    bd = _usa(monkeypatch, [_linha(1, whatsapp_falhou_em=ISO(T0 - 100), whatsapp_erro_codigo=131026)])
    recibos.registar(_estado("delivered"))
    assert bd.linhas[1]["whatsapp_entregue_em"] == ISO(T0)
    assert bd.linhas[1]["whatsapp_falhou_em"] is None and bd.linhas[1]["whatsapp_erro_codigo"] is None


def test_falha_mais_antiga_que_uma_entrega_ja_gravada_nao_marca(monkeypatch):
    bd = _usa(monkeypatch, [_linha(1, whatsapp_entregue_em=ISO(T0 + 60))])
    recibos.registar(_estado("failed", 131026))
    assert bd.linhas[1]["whatsapp_falhou_em"] is None


def test_entrega_mais_antiga_que_a_falha_nao_a_limpa(monkeypatch):
    bd = _usa(monkeypatch, [_linha(1, whatsapp_falhou_em=ISO(T0 + 60), whatsapp_erro_codigo=131026)])
    recibos.registar(_estado("delivered"))
    assert bd.linhas[1]["whatsapp_erro_codigo"] == 131026
    assert bd.linhas[1]["whatsapp_entregue_em"] == ISO(T0)


def test_quem_escreve_limpa_a_marca(monkeypatch):
    bd = _usa(monkeypatch, [_linha(1, whatsapp_falhou_em=ISO(T0), whatsapp_erro_codigo=131026)])
    recibos.limpar_falha("351912345678")
    assert bd.linhas[1]["whatsapp_falhou_em"] is None


def test_falha_da_bd_nunca_levanta(monkeypatch):
    """Antes da migration 0048 as colunas não existem: o webhook tem de devolver 200 na mesma."""
    def _rebenta():
        raise RuntimeError("coluna inexistente")
    monkeypatch.setattr(recibos, "get_supabase", _rebenta)
    recibos.registar(_estado("failed", 131026))
    recibos.limpar_falha("351912345678")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
