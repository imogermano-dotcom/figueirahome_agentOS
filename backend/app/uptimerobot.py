"""Estado do site via UptimeRobot — o utilizador já tem conta (plano grátis,
5/5 min), por isso o nosso próprio cron de uptime foi desactivado 23/09
(`docs/fases/cron-manager-fly-resumo.md`). Isto só lê o que já existe lá.

Cache de 60s em memória: o Dashboard pode ser recarregado várias vezes por
minuto, e o plano grátis do UptimeRobot limita a 10 pedidos/min.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_URL = "https://api.uptimerobot.com/v2/getMonitors"
_TIMEOUT = 10.0

# 2=up, 9=down são os que importam para o painel; os outros (0 pausado,
# 1 por verificar, 8 "parece em baixo" mas ainda a confirmar) ficam como
# "desconhecido" — não vale a pena o painel distinguir mais do que isto.
_ESTADOS = {2: "up", 9: "down"}

_cache: dict = {"em": 0.0, "dados": None}
_CACHE_TTL = 60


async def _pedir() -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_URL, data={
            "api_key": settings.uptimerobot_api_key,
            "format": "json",
            "custom_uptime_ratios": "1-7-30",
        })
        resp.raise_for_status()
        return resp.json()


def _monitor_do_site(monitores: list[dict]) -> dict | None:
    """O monitor de figueirahome.pt entre os que a conta tiver.

    Por URL, não por posição — a conta pode ter mais do que um monitor, e a
    ordem da API não é garantida. Sem correspondência, cai no primeiro (conta
    normalmente só tem este).
    """
    for m in monitores:
        if "figueirahome" in (m.get("url") or "").lower():
            return m
    return monitores[0] if monitores else None


async def estado_site() -> dict:
    """`{disponivel, status, uptime_24h, uptime_7d, uptime_30d, url, erro}`.

    `disponivel=False` sem `uptimerobot_api_key` configurada — o painel
    esconde o cartão em vez de mostrar um erro permanente.
    """
    if not settings.uptimerobot_api_key:
        return {"disponivel": False, "erro": None}

    agora = time.monotonic()
    if _cache["dados"] and agora - _cache["em"] < _CACHE_TTL:
        return _cache["dados"]

    try:
        corpo = await _pedir()
        if corpo.get("stat") != "ok":
            raise ValueError(corpo.get("error", {}).get("message", "resposta sem stat=ok"))

        monitor = _monitor_do_site(corpo.get("monitors") or [])
        if not monitor:
            resultado = {"disponivel": True, "erro": "Sem monitores na conta UptimeRobot."}
        else:
            ratios = (monitor.get("custom_uptime_ratio") or "").split("-")
            ratios = [float(r) if r else None for r in ratios] + [None, None, None]
            resultado = {
                "disponivel": True,
                "status": _ESTADOS.get(monitor.get("status"), "desconhecido"),
                "uptime_24h": ratios[0],
                "uptime_7d": ratios[1],
                "uptime_30d": ratios[2],
                "url": monitor.get("url"),
                "erro": None,
            }
    except Exception as exc:
        logger.exception("Falha a consultar o UptimeRobot")
        resultado = {"disponivel": True, "erro": f"{type(exc).__name__}: {exc}"[:300]}

    _cache.update(em=agora, dados=resultado)
    return resultado
