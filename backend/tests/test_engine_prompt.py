"""Montagem do system prompt — funções puras, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_engine_prompt.py`.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.engine import _data_de_hoje, _montar_system_prompt  # noqa: E402


def test_data_de_hoje_bate_com_o_relogio():
    hoje = datetime.now(timezone.utc)
    texto = _data_de_hoje()
    assert hoje.strftime("%d/%m/%Y") in texto
    assert "Hoje é" in texto


def test_montar_system_prompt_inclui_a_data():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "whatsapp")
    assert "base" in prompt
    assert "Hoje é" in prompt


def test_montar_system_prompt_site_acrescenta_instrucao():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "site")
    assert "chat do site" in prompt


if __name__ == "__main__":
    test_data_de_hoje_bate_com_o_relogio()
    test_montar_system_prompt_inclui_a_data()
    test_montar_system_prompt_site_acrescenta_instrucao()
    print("test_engine_prompt OK")
