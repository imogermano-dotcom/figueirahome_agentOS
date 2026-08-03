"""Custo de uma chamada à API da Anthropic, a partir do `usage` da resposta.

Preços confirmados na documentação oficial da Anthropic (não de memória),
em USD por milhão de tokens. Cache: leitura ~0,1x do preço de input,
escrita 1,25x (TTL de 5 minutos, que é o que o `engine.py` usa).

O custo é calculado no momento da chamada e **gravado** em
`agente_interacoes.custo_usd` — ver o comentário na migration 0016 para
o porquê de não ser recalculado a partir dos tokens.

# ponytail: preços num dict, não numa tabela da BD. Mover só quando houver
# mais do que um modelo em uso ao mesmo tempo.
"""

import logging

logger = logging.getLogger(__name__)

_MILHAO = 1_000_000

# USD por milhão de tokens.
PRECOS: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}

_FACTOR_CACHE_READ = 0.1
_FACTOR_CACHE_WRITE = 1.25


def somar_usage(acumulado: dict, usage: dict | None) -> dict:
    """Soma o `usage` de uma resposta ao acumulado do turno.

    Um turno com duas tools são três chamadas à API; o custo do turno é a
    soma das três, não o da última.
    """
    if not usage:
        return acumulado
    for origem, destino in (
        ("input_tokens", "tokens_input"),
        ("output_tokens", "tokens_output"),
        ("cache_read_input_tokens", "tokens_cache_read"),
        ("cache_creation_input_tokens", "tokens_cache_write"),
    ):
        acumulado[destino] = acumulado.get(destino, 0) + (usage.get(origem) or 0)
    return acumulado


def calcular_custo(tokens: dict, modelo: str) -> float:
    """Custo em USD. Modelo desconhecido devolve 0 e regista aviso.

    Devolver 0 em vez de rebentar é deliberado: isto corre no caminho de
    resposta ao cliente, e um preço em falta nunca pode derrubar uma conversa.
    O aviso no log é que assinala o problema.
    """
    preco = PRECOS.get(modelo)
    if not preco:
        logger.warning("Sem preço para o modelo '%s' — custo registado como 0.", modelo)
        return 0.0

    entrada = preco["input"] / _MILHAO
    saida = preco["output"] / _MILHAO

    return (
        tokens.get("tokens_input", 0) * entrada
        + tokens.get("tokens_output", 0) * saida
        + tokens.get("tokens_cache_read", 0) * entrada * _FACTOR_CACHE_READ
        + tokens.get("tokens_cache_write", 0) * entrada * _FACTOR_CACHE_WRITE
    )
