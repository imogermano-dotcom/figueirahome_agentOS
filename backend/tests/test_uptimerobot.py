"""Estado do site via UptimeRobot — parsing puro + `estado_site` sem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_uptimerobot.py`.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.uptimerobot as uptimerobot  # noqa: E402
from app.uptimerobot import _monitor_do_site  # noqa: E402


def test_monitor_do_site_por_url():
    monitores = [
        {"url": "https://outro-site.pt", "id": 1},
        {"url": "https://www.figueirahome.pt", "id": 2},
    ]
    assert _monitor_do_site(monitores)["id"] == 2


def test_monitor_do_site_cai_no_primeiro_sem_correspondencia():
    monitores = [{"url": "https://outro-site.pt", "id": 1}]
    assert _monitor_do_site(monitores)["id"] == 1
    assert _monitor_do_site([]) is None


def test_sem_api_key_devolve_indisponivel():
    original = uptimerobot.settings.uptimerobot_api_key
    try:
        uptimerobot.settings.uptimerobot_api_key = ""
        resultado = asyncio.run(uptimerobot.estado_site())
    finally:
        uptimerobot.settings.uptimerobot_api_key = original
    assert resultado == {"disponivel": False, "erro": None}


def test_estado_site_parseia_o_monitor_certo(monkeypatch=None):
    """Sem fixture de monkeypatch (ficheiro corre também sem pytest) — patch manual."""
    original_key = uptimerobot.settings.uptimerobot_api_key
    original_pedir = uptimerobot._pedir
    original_cache = dict(uptimerobot._cache)

    async def _fake_pedir():
        return {
            "stat": "ok",
            "monitors": [{
                "url": "https://www.figueirahome.pt",
                "status": 2,
                "custom_uptime_ratio": "100.000-99.950-99.900",
            }],
        }

    try:
        uptimerobot.settings.uptimerobot_api_key = "fake-key"
        uptimerobot._pedir = _fake_pedir
        uptimerobot._cache.update(em=0.0, dados=None)
        resultado = asyncio.run(uptimerobot.estado_site())
    finally:
        uptimerobot.settings.uptimerobot_api_key = original_key
        uptimerobot._pedir = original_pedir
        uptimerobot._cache.update(original_cache)

    assert resultado["disponivel"] is True
    assert resultado["status"] == "up"
    assert resultado["uptime_24h"] == 100.0
    assert resultado["uptime_7d"] == 99.95
    assert resultado["uptime_30d"] == 99.9
    assert resultado["erro"] is None


if __name__ == "__main__":
    test_monitor_do_site_por_url()
    test_monitor_do_site_cai_no_primeiro_sem_correspondencia()
    test_sem_api_key_devolve_indisponivel()
    test_estado_site_parseia_o_monitor_certo()
    print("test_uptimerobot OK")
