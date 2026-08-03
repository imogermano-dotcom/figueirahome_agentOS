"""Cálculo de custo. Funções puras, sem DB nem rede.

    python backend/tests/test_custos.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.custos import calcular_custo, somar_usage  # noqa: E402

MODELO = "claude-sonnet-4-6"  # $3,00 input / $15,00 output por milhão


def test_input_e_output():
    # 1M input = $3,00 exactos
    assert calcular_custo({"tokens_input": 1_000_000}, MODELO) == 3.00
    # 1M output = $15,00 exactos
    assert calcular_custo({"tokens_output": 1_000_000}, MODELO) == 15.00
    # 1000 input + 500 output = 0,003 + 0,0075
    assert round(calcular_custo({"tokens_input": 1000, "tokens_output": 500}, MODELO), 8) == 0.0105


def test_cache_read_custa_um_decimo_do_input():
    normal = calcular_custo({"tokens_input": 1_000_000}, MODELO)
    cache = calcular_custo({"tokens_cache_read": 1_000_000}, MODELO)
    assert round(cache, 8) == round(normal * 0.1, 8)
    assert round(cache, 8) == 0.30


def test_cache_write_custa_um_quarto_a_mais():
    normal = calcular_custo({"tokens_input": 1_000_000}, MODELO)
    escrita = calcular_custo({"tokens_cache_write": 1_000_000}, MODELO)
    assert round(escrita, 8) == round(normal * 1.25, 8)
    assert round(escrita, 8) == 3.75


def test_modelo_desconhecido_nao_rebenta():
    # Corre no caminho de resposta ao cliente: um preço em falta não pode
    # derrubar uma conversa.
    assert calcular_custo({"tokens_input": 999_999}, "modelo-que-nao-existe") == 0.0


def test_tokens_em_falta_valem_zero():
    assert calcular_custo({}, MODELO) == 0.0


def test_somar_usage_acumula_entre_iteracoes():
    """Um turno com tools são várias chamadas à API — o custo é a soma."""
    acc: dict = {}
    somar_usage(acc, {"input_tokens": 100, "output_tokens": 50,
                      "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5})
    somar_usage(acc, {"input_tokens": 200, "output_tokens": 80,
                      "cache_read_input_tokens": 20, "cache_creation_input_tokens": 0})
    assert acc == {"tokens_input": 300, "tokens_output": 130,
                   "tokens_cache_read": 30, "tokens_cache_write": 5}


def test_somar_usage_tolera_ausencias():
    acc: dict = {}
    somar_usage(acc, None)                      # chamada falhada, sem usage
    somar_usage(acc, {})                        # usage vazio
    somar_usage(acc, {"input_tokens": None})    # campo presente mas nulo
    somar_usage(acc, {"input_tokens": 7})
    assert acc["tokens_input"] == 7


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"  ok  {nome}")
    print("test_custos OK")
