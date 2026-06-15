import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx

from app.agents.broker.conversation import load_conversation, save_conversation
from app.agents.broker.tools import TOOL_DEFINITIONS, execute_tool
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_SYSTEM_BASE = """És o assistente do broker da agência imobiliária Figueirahome, em Portugal.
Respondes sempre em Português de Portugal, de forma profissional e directa.
Tens acesso à base de dados da agência e podes consultar clientes, imóveis e leads.
Quando precisares de informação da base de dados, usa as tools disponíveis.
As tuas respostas devem ser claras, estruturadas e úteis para o broker.
"""

_MAX_TOOL_ITERATIONS = 5


async def _load_config() -> str:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _fetch():
        return (
            supabase.table("agente_config")
            .select("persona,instrucoes")
            .eq("agente", "broker")
            .single()
            .execute()
        )

    try:
        resp = await loop.run_in_executor(None, _fetch)
        data = resp.data or {}
        persona = data.get("persona", "")
        instrucoes = data.get("instrucoes", "")
        extra = f"\nPersona: {persona}\n{instrucoes}" if persona else ""
        return _SYSTEM_BASE + extra
    except Exception:
        logger.warning("Config broker não encontrada — usando sistema base.")
        return _SYSTEM_BASE


async def get_response(participante: str, canal: str, mensagem_user: str) -> str:
    conversa_id, mensagens = await load_conversation(canal, participante)
    system_prompt = await _load_config()

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "user", "content": mensagem_user, "timestamp": now})

    # Build Claude messages (only role + content — strip timestamp)
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in mensagens]

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    response_text = "Ocorreu um erro. Tenta novamente."

    async with httpx.AsyncClient(timeout=60.0) as client:
        for _ in range(_MAX_TOOL_ITERATIONS):
            payload = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "system": system_prompt,
                "tools": TOOL_DEFINITIONS,
                "messages": claude_messages,
            }

            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            stop_reason = data.get("stop_reason")
            content_blocks = data.get("content", [])

            if stop_reason == "tool_use":
                # Add assistant message with all content blocks
                claude_messages.append({"role": "assistant", "content": content_blocks})

                # Execute all tool calls and collect results
                tool_results = []
                for block in content_blocks:
                    if block.get("type") == "tool_use":
                        tool_result = await execute_tool(block["name"], block.get("input", {}))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": tool_result,
                        })

                claude_messages.append({"role": "user", "content": tool_results})
                continue

            # Final text response
            for block in content_blocks:
                if block.get("type") == "text":
                    response_text = block["text"]
                    break
            break

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "assistant", "content": response_text, "timestamp": now})

    try:
        conversa_id = await save_conversation(conversa_id, canal, participante, mensagens)
    except Exception:
        logger.exception("Erro ao guardar conversa canal=%s participante=%s", canal, participante)

    return response_text
