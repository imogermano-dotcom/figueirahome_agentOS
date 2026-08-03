"""Motor único dos assistentes.

Substitui três loops agênticos quase idênticos (`broker/claude_agent.py`,
`voice/whatsapp_intake.py` e, por herança, o de voz). Diferiam em constantes
e em duas capacidades que só uma das cópias tinha — prompt caching e tool
forcing — e que aqui passam a valer para todos.

Chamado por:
* `agents/broker/channels/whatsapp/webhook.py` — WhatsApp, com router
* `api/broker.py` — chat web do painel, com assistente escolhido à mão
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.agents.broker.assistants import (
    ASSISTENTES,
    MAX_TOKENS,
    MENSAGEM_INATIVO,
    load_config,
)
from app.agents.broker.conversation import load_conversation, save_conversation
from app.agents.broker.custos import calcular_custo, somar_usage
from app.agents.broker.guards import normalizar_telefone, variantes_telefone
from app.agents.broker.router import route
from app.agents.broker.tools import execute_tool, tools_para
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.4  # spec §2.3: consistente sem ser robótico
_MAX_TOOL_ITERATIONS = 4  # A1 encadeia ficha -> guardar -> agendar
_ERRO = "Ocorreu um erro. Tenta novamente."


def _perfil_cliente(telefone: str) -> str:
    """Contexto do cliente já conhecido, para o prompt. Só faz sentido com telefone.

    Procura pelas mesmas variantes que o dedup (`guards.variantes_telefone`):
    as linhas antigas guardam o número como a Meta o enviou (`351…`), as novas
    já ficam normalizadas. Procurar só por uma forma perdia metade delas.
    """
    try:
        resp = (
            get_supabase()
            .table("agente_clientes")
            .select("nome,tipo_interesse,orcamento,zona_preferida")
            .in_("telefone", variantes_telefone(telefone))
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception("Erro ao procurar cliente %s", telefone)
        return ""

    if not resp.data:
        return ""

    c = resp.data[0]
    campos = [
        f"{rotulo}: {c[campo]}"
        for rotulo, campo in (
            ("Nome", "nome"), ("Interesse", "tipo_interesse"),
            ("Orçamento", "orcamento"), ("Zona", "zona_preferida"),
        )
        if c.get(campo)
    ]
    if not campos:
        return ""
    return (
        "\n\nEste cliente já está registado: " + " | ".join(campos) +
        "\nCumprimenta-o pelo nome e não voltes a pedir dados que já temos."
    )


# Tools cujos argumentos são critérios de pesquisa e nada mais. Só destas se
# guardam os `input` em `agente_interacoes.tools_detalhe`.
#
# `guardar_dados_cliente`, `agendar_visita` e `escalar_para_humano` recebem
# nome, telefone e email — copiá-los para cá espalharia dados pessoais por uma
# segunda tabela sem necessidade. Dessas guarda-se o nome da tool e mais nada.
#
# Allowlist e não blocklist de propósito: uma tool nova entra por omissão no
# lado seguro. Acrescentar aqui exige olhar para o schema dela primeiro.
_TOOLS_INPUT_SEGURO = frozenset({"pesquisar_imoveis", "ficha_imovel"})


def _detalhe_tool(bloco: dict) -> dict:
    """Nome da tool, e os argumentos apenas quando não carregam PII."""
    nome = bloco.get("name", "")
    if nome in _TOOLS_INPUT_SEGURO:
        return {"nome": nome, "input": bloco.get("input") or {}}
    return {"nome": nome}


async def _registar_interacao(dados: dict) -> None:
    """Grava uma linha em `agente_interacoes`.

    Engolir a excepção é deliberado: isto corre depois de a resposta estar
    pronta, e observabilidade nunca pode derrubar uma conversa com um cliente.
    Se a tabela não existir (migration 0016 por aplicar), fica só o aviso.
    """

    def _inserir():
        get_supabase().table("agente_interacoes").insert(
            {k: v for k, v in dados.items() if v is not None}
        ).execute()

    try:
        await asyncio.get_event_loop().run_in_executor(None, _inserir)
    except Exception:
        logger.exception("Falha ao registar interacao (%s)", dados.get("agente"))


async def responder(
    canal: str,
    participante: str,
    mensagem: str,
    agente: str | None = None,
) -> str:
    """Responde a uma mensagem e persiste a conversa.

    `agente=None` deixa o router decidir (e a decisão fica colada à thread).
    """
    conversa_id, mensagens, agente_atual = await load_conversation(canal, participante)

    agente = agente or route(mensagem, agente_atual)
    if agente not in ASSISTENTES:
        logger.warning("Assistente '%s' desconhecido — fallback para o router.", agente)
        agente = route(mensagem, None)
    spec = ASSISTENTES[agente]

    extra, ativo = await load_config(agente)
    if not ativo:
        logger.info("Assistente %s inactivo — sem chamada à API.", agente)
        return MENSAGEM_INATIVO

    telefone = normalizar_telefone(participante) if canal == "whatsapp" else None
    perfil = ""
    if telefone:
        perfil = await asyncio.get_event_loop().run_in_executor(
            None, _perfil_cliente, telefone
        )

    system_prompt = spec["prompt"] + perfil + extra
    contexto = {
        "canal": canal,
        "telefone": telefone,
        "origem": canal,
        "agente": agente,
        # None no 1.º turno de uma conversa nova: o id só existe depois do
        # save_conversation, no fim do turno. A tarefa fica sem conversa mas
        # com agente — preferível a inverter a ordem de gravação só por isto.
        "conversa_id": conversa_id,
    }

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "user", "content": mensagem, "timestamp": now})
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in mensagens]

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "prompt-caching-2024-07-31",
        "content-type": "application/json",
    }
    # System como lista com cache_control: cache hits custam 10% do preço.
    system_payload = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
    ]

    forcar = spec.get("force")
    # Sem este forcing o Claude ignorava as tools e prometia callbacks de
    # consultor — comportamento observado em produção (CLAUDE.md).
    forcar_agora = bool(forcar and forcar[1].search(mensagem))

    resposta = _ERRO

    # Instrumentação do turno. O `usage` chega em cada resposta da API e antes
    # era descartado — sem ele o custo é incalculável.
    tokens: dict[str, int] = {}
    tools_usadas: list[str] = []
    tools_detalhe: list[dict] = []
    iteracoes = 0
    erro: str | None = None
    inicio = time.monotonic()

    async with httpx.AsyncClient(timeout=60.0) as client:
        for iteracao in range(_MAX_TOOL_ITERATIONS):
            iteracoes = iteracao + 1
            payload = {
                "model": _MODEL,
                "max_tokens": MAX_TOKENS.get(canal, 512),
                "temperature": _TEMPERATURE,
                "system": system_payload,
                "tools": tools_para(spec["tools"]),
                "messages": claude_messages,
            }
            if forcar_agora and iteracao == 0:
                payload["tool_choice"] = {"type": "tool", "name": forcar[0]}

            try:
                http_resp = await client.post(_URL, headers=headers, json=payload)
                http_resp.raise_for_status()
            except Exception as exc:
                logger.exception("Erro na API Anthropic (%s, %s)", agente, participante)
                erro = f"{type(exc).__name__}: {exc}"[:500]
                break

            data = http_resp.json()
            somar_usage(tokens, data.get("usage"))
            blocos = data.get("content", [])

            if data.get("stop_reason") == "tool_use":
                claude_messages.append({"role": "assistant", "content": blocos})
                resultados = []
                for bloco in blocos:
                    if bloco.get("type") != "tool_use":
                        continue
                    tools_usadas.append(bloco["name"])
                    tools_detalhe.append(_detalhe_tool(bloco))
                    saida = await execute_tool(
                        bloco["name"], bloco.get("input", {}), contexto
                    )
                    resultados.append({
                        "type": "tool_result",
                        "tool_use_id": bloco["id"],
                        "content": saida,
                    })
                claude_messages.append({"role": "user", "content": resultados})
                continue

            for bloco in blocos:
                if bloco.get("type") == "text":
                    resposta = bloco["text"]
                    break
            break

    latencia_ms = int((time.monotonic() - inicio) * 1000)

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "assistant", "content": resposta, "timestamp": now})

    try:
        conversa_id = await save_conversation(
            conversa_id, canal, participante, mensagens, agente
        )
    except Exception:
        logger.exception("Erro ao guardar conversa %s/%s", canal, participante)

    await _registar_interacao({
        "conversa_id": conversa_id,
        "agente": agente,
        "canal": canal,
        "modelo": _MODEL,
        **tokens,
        "custo_usd": calcular_custo(tokens, _MODEL),
        "latencia_ms": latencia_ms,
        "iteracoes": iteracoes,
        "tools_usadas": tools_usadas or None,
        "tools_detalhe": tools_detalhe or None,
        "tool_forcada": forcar_agora,
        "erro": erro,
    })

    return resposta
