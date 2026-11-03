"""Resumo diário das tarefas por tratar (`docs/fases/tarefas-pendentes-plano.md`). Sem rede."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import tarefas_resumo as tr  # noqa: E402
from app.agents.broker.guards import _TAREFA_QUALIFICADA  # noqa: E402

AGORA = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)
AGORA_REAL = datetime.now(timezone.utc)  # o endpoint usa o relógio


def _t(horas, ref=AGORA, **kw):
    base = {"titulo": "Escalada — Teste", "tipo": "escalar", "estado": "pendente", "agente": "a1_vendedor",
            "imovel_ref": None, "criado_em": (ref - timedelta(hours=horas)).isoformat()}
    return base | kw


def test_janela_12h_a_7_dias():
    dentro, antigas = tr.selecionar([_t(11), _t(13), _t(24 * 6), _t(24 * 8), _t(24 * 30)], AGORA)
    assert len(dentro) == 2 and antigas == 2


def test_so_pendentes_dos_tipos_que_pedem_pessoa():
    tarefas = [_t(20, estado="concluida"), _t(20, tipo="visita"), _t(20, tipo="lead_ego"),
               _t(20, tipo="sync_imovel"), _t(20, tipo=None, titulo="eGO reportou alteração")]
    dentro, _ = tr.selecionar(tarefas, AGORA)
    assert [t["tipo"] for t in dentro] == ["visita", "lead_ego"]


def test_lead_qualificada_antiga_sem_tipo_conta():
    dentro, _ = tr.selecionar([_t(20, tipo=None, agente=None, titulo=f"{_TAREFA_QUALIFICADA} — Teste")], AGORA)
    assert len(dentro) == 1


def test_texto_agrupa_por_assistente_e_avisa_das_antigas():
    dentro, antigas = tr.selecionar(
        [_t(13, imovel_ref="FH0001"), _t(30, agente="a3_recrutamento"), _t(24 * 9)], AGORA)
    texto = tr.texto_do_resumo(dentro, antigas, AGORA)
    assert texto.index("Compra") < texto.index("Recrutamento")
    assert "há 13 h · escalar · FH0001" in texto and "há 30 h" in texto
    assert "+1 pendente(s) com mais de 7 dias" in texto


def test_sem_pendentes_na_janela_nao_envia(monkeypatch):
    import asyncio

    monkeypatch.setattr(tr, "ler_pendentes", lambda: [_t(2, AGORA_REAL), _t(24 * 9, AGORA_REAL)])
    monkeypatch.setattr(tr, "notificar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia enviar")))
    r = asyncio.run(tr.resumo_de_pendentes(acesso=None))
    assert r == {"pendentes": 0, "fora_da_janela": 1, "enviado": False}


def test_envia_uma_vez_e_dry_nao_envia(monkeypatch):
    import asyncio

    enviados = []
    monkeypatch.setattr(tr, "ler_pendentes", lambda: [_t(13, AGORA_REAL)])
    monkeypatch.setattr(tr, "notificar", lambda assunto, corpo: enviados.append(assunto))
    assert asyncio.run(tr.resumo_de_pendentes(dry=1, acesso=None))["enviado"] is False and enviados == []
    r = asyncio.run(tr.resumo_de_pendentes(acesso=None))
    assert r["enviado"] is True and enviados == ["Tarefas por tratar: 1"]
