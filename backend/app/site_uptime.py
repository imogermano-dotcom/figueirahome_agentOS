"""Uptime do site público figueirahome.pt — alerta se cair, avisa quando volta.

Reaproveita `agente_sync_log` (`tipo='site_uptime'`) em vez de tabela nova, e
`notificacoes.notificar` (Resend) em vez de canal novo — mesmo padrão do
`nudge.py` e dos syncs eGO. Cron via GitHub Actions, `X-Automacao-Secret`
(ver `docs/fases/uptime-figueirahome-plano.md`).
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.db.supabase_client import get_supabase
from app.notificacoes import notificar

logger = logging.getLogger(__name__)

SITE_URL = "https://www.figueirahome.pt"
_TIMEOUT = 10.0
_LIMIAR_FALHAS = 3
_TIPO = "site_uptime"


async def _verificar_url() -> dict:
    inicio = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(SITE_URL)
        return {
            "ok": resp.status_code == 200,
            "status": resp.status_code,
            "latencia_ms": int((time.monotonic() - inicio) * 1000),
            "erro": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "latencia_ms": int((time.monotonic() - inicio) * 1000),
            "erro": f"{type(exc).__name__}: {exc}"[:300],
        }


def _contar_falhas_no_topo(historico_ok: list[bool]) -> int:
    """`historico_ok[0]` é o mais recente. Falhas seguidas a partir do topo."""
    n = 0
    for ok in historico_ok:
        if ok:
            break
        n += 1
    return n


def _historico_ok(linhas: list[dict]) -> list[bool]:
    return [bool((linha.get("resumo") or {}).get("ok")) for linha in linhas]


async def verificar_site() -> dict:
    resultado = await _verificar_url()

    def _inserir():
        get_supabase().table("agente_sync_log").insert({
            "tipo": _TIPO,
            "executado_em": datetime.now(timezone.utc).isoformat(),
            "resumo": resultado,
            "origem": "cron",
        }).execute()

    def _historico():
        return (
            get_supabase().table("agente_sync_log")
            .select("resumo,executado_em")
            .eq("tipo", _TIPO)
            .order("executado_em", desc=True)
            .limit(_LIMIAR_FALHAS + 1)
            .execute()
        )

    historico_ok = [resultado["ok"]]
    try:
        await asyncio.get_event_loop().run_in_executor(None, _inserir)
        resp = await asyncio.get_event_loop().run_in_executor(None, _historico)
        historico_ok = _historico_ok(resp.data or [])
    except Exception:
        logger.exception("Falha a gravar/ler o histórico de uptime — o check em si correu.")

    alerta = None
    if not resultado["ok"] and _contar_falhas_no_topo(historico_ok) == _LIMIAR_FALHAS:
        alerta = "queda"
    elif resultado["ok"] and _contar_falhas_no_topo(historico_ok[1:]) >= _LIMIAR_FALHAS:
        alerta = "recuperacao"

    if alerta == "queda":
        motivo = resultado["erro"] or f"HTTP {resultado['status']}"
        notificar(
            f"🔴 {SITE_URL} está em baixo",
            f"{_LIMIAR_FALHAS} verificações seguidas falharam (cron de 5 em 5 min).\n\n"
            f"Último erro: {motivo}",
        )
    elif alerta == "recuperacao":
        notificar(
            f"🟢 {SITE_URL} voltou ao ar",
            f"Respondeu com HTTP {resultado['status']} depois de estar em baixo.",
        )

    return {**resultado, "alerta": alerta}


def demo() -> None:
    """`python -m app.site_uptime` de `backend/`"""
    assert _contar_falhas_no_topo([False, False, False, True]) == 3
    assert _contar_falhas_no_topo([True, False, False]) == 0
    assert _contar_falhas_no_topo([False]) == 1
    assert _contar_falhas_no_topo([]) == 0
    assert _historico_ok([{"resumo": {"ok": True}}, {"resumo": {"ok": False}}, {"resumo": None}]) == [True, False, False]
    print("site_uptime OK")


if __name__ == "__main__":
    demo()
