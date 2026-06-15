import asyncio
import hashlib
import logging
from datetime import datetime, timezone

import httpx

from app.agents.broker.conversation import load_conversation, save_conversation
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_SYSTEM_NOVO_CLIENTE = """És a assistente da agência imobiliária Figueirahome, em Portugal.
Respondes por WhatsApp, em Português de Portugal, de forma natural e cordial.
O teu objectivo é recolher os seguintes dados do cliente:
  - Nome completo
  - Número de telefone de contacto (se diferente do WhatsApp)
  - Tipo de interesse: compra, arrendamento, venda ou outro
  - Orçamento (em euros)
  - Zona ou localização preferida

Instruções:
- Faz perguntas de forma natural, uma de cada vez.
- Não termines a conversa sem teres pelo menos o nome e o tipo de interesse.
- Quando tiveres todos os dados, confirma-os com o cliente e despede-te de forma cordial.
- Usa a tool guardar_dados_cliente quando tiveres dados suficientes para registar.
- As tuas respostas devem ser directas e adequadas para mensagens de texto.
"""

_SYSTEM_CLIENTE_EXISTENTE = """És a assistente da agência imobiliária Figueirahome, em Portugal.
Respondes por WhatsApp, em Português de Portugal, de forma natural e cordial.

Este cliente já está registado na nossa base de dados:
{perfil}

Instruções:
- Cumprimenta pelo nome e continua a conversa de forma natural.
- NÃO voltes a pedir dados que já temos (nome, tipo de interesse, etc.).
- Podes actualizar dados se o cliente mencionar mudanças (ex: novo orçamento, nova zona).
- Se o cliente pedir informações sobre imóveis ou o mercado, responde de forma útil e profissional.
- Usa a tool guardar_dados_cliente se o cliente fornecer novos dados relevantes a actualizar.
- As tuas respostas devem ser directas e adequadas para mensagens de texto.
"""

_SAVE_TOOL = [
    {
        "name": "guardar_dados_cliente",
        "description": "Guarda os dados recolhidos do cliente na base de dados. Chama esta tool quando tiveres pelo menos o nome e o tipo de interesse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Nome do cliente"},
                "telefone": {"type": "string", "description": "Telefone de contacto (se diferente do WhatsApp)"},
                "tipo_interesse": {
                    "type": "string",
                    "enum": ["compra", "arrendamento", "venda", "outro"],
                },
                "orcamento": {"type": "number", "description": "Orçamento em euros"},
                "zona_preferida": {"type": "string"},
                "resumo": {"type": "string", "description": "Resumo breve da conversa"},
            },
            "required": ["nome", "tipo_interesse", "resumo"],
        },
    }
]

_MAX_TOOL_ITERATIONS = 3


def _lookup_cliente(telefone: str) -> dict | None:
    supabase = get_supabase()
    resp = (
        supabase.table("agente_clientes")
        .select("nome,telefone,tipo_interesse,orcamento,zona_preferida")
        .eq("telefone", telefone)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


async def _load_config(from_number: str) -> str:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    cliente = await loop.run_in_executor(None, _lookup_cliente, from_number)

    def _fetch():
        return (
            supabase.table("agente_config")
            .select("persona,instrucoes")
            .eq("agente", "voz")
            .single()
            .execute()
        )

    try:
        resp = await loop.run_in_executor(None, _fetch)
        data = resp.data or {}
        persona = data.get("persona", "")
        instrucoes = data.get("instrucoes", "")
        extra = f"\nPersona: {persona}\n{instrucoes}" if persona else ""
    except Exception:
        logger.warning("Config voz não encontrada — usando sistema base.")
        extra = ""

    if cliente:
        campos = []
        if cliente.get("nome"):
            campos.append(f"Nome: {cliente['nome']}")
        if cliente.get("tipo_interesse"):
            campos.append(f"Interesse: {cliente['tipo_interesse']}")
        if cliente.get("orcamento"):
            campos.append(f"Orçamento: {cliente['orcamento']}€")
        if cliente.get("zona_preferida"):
            campos.append(f"Zona: {cliente['zona_preferida']}")
        perfil = " | ".join(campos) if campos else "dados incompletos"
        return _SYSTEM_CLIENTE_EXISTENTE.format(perfil=perfil) + extra

    return _SYSTEM_NOVO_CLIENTE + extra


def _save_to_db(dados: dict, from_number: str) -> None:
    supabase = get_supabase()
    telefone = dados.get("telefone") or from_number

    existing = (
        supabase.table("agente_clientes")
        .select("id")
        .eq("telefone", telefone)
        .limit(1)
        .execute()
    )
    cliente_data = {
        "nome": dados.get("nome"),
        "telefone": telefone,
        "tipo_interesse": dados.get("tipo_interesse"),
        "orcamento": dados.get("orcamento"),
        "zona_preferida": dados.get("zona_preferida"),
        "origem": "whatsapp",
    }
    cliente_data = {k: v for k, v in cliente_data.items() if v is not None}

    if existing.data:
        cliente_id = existing.data[0]["id"]
        supabase.table("agente_clientes").update(cliente_data).eq("id", cliente_id).execute()
    else:
        result = supabase.table("agente_clientes").insert(cliente_data).execute()
        cliente_id = result.data[0]["id"] if result.data else None

    if cliente_id and dados.get("tipo_interesse"):
        supabase.table("agente_leads").insert(
            {
                "cliente_id": cliente_id,
                "estado": "novo",
                "notas": dados.get("resumo"),
            }
        ).execute()

    logger.info("Cliente WhatsApp guardado: %s", telefone)


async def get_response(from_number: str, mensagem_user: str) -> str:
    conversa_id, mensagens = await load_conversation("whatsapp", from_number)
    system_prompt = await _load_config(from_number)

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "user", "content": mensagem_user, "timestamp": now})

    claude_messages = [{"role": m["role"], "content": m["content"]} for m in mensagens]

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    response_text = "Ocorreu um erro. Tenta novamente."
    dados_guardados = False

    async with httpx.AsyncClient(timeout=60.0) as client:
        for _ in range(_MAX_TOOL_ITERATIONS):
            payload = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 512,
                "system": system_prompt,
                "tools": _SAVE_TOOL,
                "messages": claude_messages,
            }

            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            stop_reason = data.get("stop_reason")
            content_blocks = data.get("content", [])

            if stop_reason == "tool_use":
                claude_messages.append({"role": "assistant", "content": content_blocks})
                tool_results = []

                for block in content_blocks:
                    if block.get("type") == "tool_use" and block["name"] == "guardar_dados_cliente":
                        dados = block.get("input", {})
                        loop = asyncio.get_event_loop()
                        try:
                            await loop.run_in_executor(None, _save_to_db, dados, from_number)
                            dados_guardados = True
                            tool_result_content = "Dados guardados com sucesso."
                        except Exception:
                            logger.exception("Erro ao guardar dados WhatsApp de %s", from_number)
                            tool_result_content = "Erro ao guardar dados."

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": tool_result_content,
                        })

                claude_messages.append({"role": "user", "content": tool_results})
                continue

            for block in content_blocks:
                if block.get("type") == "text":
                    response_text = block["text"]
                    break
            break

    now = datetime.now(timezone.utc).isoformat()
    mensagens.append({"role": "assistant", "content": response_text, "timestamp": now})

    try:
        await save_conversation(conversa_id, "whatsapp", from_number, mensagens)
    except Exception:
        logger.exception("Erro ao guardar conversa WhatsApp %s", from_number)

    return response_text
