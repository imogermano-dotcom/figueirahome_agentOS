import asyncio
import hashlib
import logging
from datetime import datetime, timezone

import httpx

from app.agents.broker.conversation import load_conversation, save_conversation
from app.config import settings
from app.db.supabase_client import get_supabase, get_supabase_imoveis

logger = logging.getLogger(__name__)

_SYSTEM_NOVO_CLIENTE = """És a assistente da agência imobiliária Figueirahome, em Portugal.
Respondes por WhatsApp, em Português de Portugal, de forma natural e cordial.

PRIORIDADE 1 — MOSTRAR IMÓVEIS REAIS:
Se o cliente mencionar qualquer critério (tipo, quartos, zona, preço, compra ou arrendamento), chama IMEDIATAMENTE a tool pesquisar_imoveis e apresenta os resultados. Nunca prometas que "um consultor vai entrar em contacto" — mostra imóveis reais do portefólio.

PRIORIDADE 2 — RECOLHER DADOS:
Após mostrar imóveis (ou se o cliente não tiver critérios), recolhe de forma natural:
  - Nome completo
  - Tipo de interesse: compra, arrendamento, venda ou outro
  - Orçamento (em euros)
  - Zona ou localização preferida

Instruções:
- Faz perguntas uma de cada vez, nunca em bloco.
- Usa guardar_dados_cliente quando tiveres pelo menos nome e tipo de interesse.
- NUNCA digas que um consultor vai ligar — és tu que ajudas directamente, com imóveis reais.
- Respostas curtas e directas, adequadas para WhatsApp.
"""

_SYSTEM_CLIENTE_EXISTENTE = """És a assistente da agência imobiliária Figueirahome, em Portugal.
Respondes por WhatsApp, em Português de Portugal, de forma natural e cordial.

Este cliente já está registado na nossa base de dados:
{perfil}

Instruções:
- Cumprimenta pelo nome e continua a conversa de forma natural.
- NÃO voltes a pedir dados que já temos (nome, tipo de interesse, etc.).
- Se o cliente mencionar tipo/quartos/zona/preço, chama IMEDIATAMENTE pesquisar_imoveis e mostra resultados reais. NUNCA prometas callback de consultor.
- Podes actualizar dados se o cliente mencionar mudanças (ex: novo orçamento, nova zona).
- Usa guardar_dados_cliente se o cliente fornecer novos dados relevantes.
- Respostas curtas e directas, adequadas para WhatsApp.
"""

_SEARCH_TOOL = {
    "name": "pesquisar_imoveis",
    "description": "Pesquisa imóveis disponíveis na base de dados da agência. Usa quando o cliente pedir imóveis, quiser saber o que há disponível, ou mencionar tipo, quartos, zona ou preço.",
    "input_schema": {
        "type": "object",
        "properties": {
            "natureza": {
                "type": "string",
                "description": "Tipo de imóvel: Apartamento, Moradia, Terreno, Comercial, etc.",
            },
            "quartos": {
                "type": "integer",
                "description": "Número de quartos (T0=0, T1=1, T2=2, etc.)",
            },
            "concelho": {
                "type": "string",
                "description": "Concelho ou localização (ex: Figueira da Foz, Coimbra)",
            },
            "tipo_negocio": {
                "type": "string",
                "enum": ["venda", "arrendamento"],
                "description": "Se é para compra (venda) ou arrendamento",
            },
            "preco_max": {
                "type": "number",
                "description": "Preço máximo em euros",
            },
        },
        "required": [],
    },
}

_SAVE_TOOL = [
    _SEARCH_TOOL,
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
    },
]

_MAX_TOOL_ITERATIONS = 3


def _pesquisar_imoveis(filtros: dict) -> str:
    supabase = get_supabase_imoveis()
    query = supabase.table("imoveis").select(
        "imovel_ref,natureza,quartos,area_util,venda_preco,arrendamento_preco,concelho,freguesia,descricao,disponibilidade"
    )

    natureza = filtros.get("natureza")
    quartos = filtros.get("quartos")
    concelho = filtros.get("concelho")
    tipo_negocio = filtros.get("tipo_negocio")
    preco_max = filtros.get("preco_max")

    if natureza:
        query = query.ilike("natureza", f"%{natureza}%")
    if quartos is not None:
        query = query.eq("quartos", quartos)
    if concelho:
        query = query.ilike("concelho", f"%{concelho}%")
    if tipo_negocio == "venda":
        query = query.gt("venda_preco", 0)
        if preco_max:
            query = query.lte("venda_preco", preco_max)
    elif tipo_negocio == "arrendamento":
        query = query.gt("arrendamento_preco", 0)
        if preco_max:
            query = query.lte("arrendamento_preco", preco_max)

    resp = query.limit(5).execute()
    if not resp.data:
        return "Não foram encontrados imóveis com esses critérios."

    linhas = []
    for r in resp.data:
        preco = ""
        if tipo_negocio == "arrendamento" and r.get("arrendamento_preco"):
            preco = f"{r['arrendamento_preco']}€/mês"
        elif r.get("venda_preco") and r["venda_preco"] > 0:
            preco = f"{r['venda_preco']}€"

        partes = [
            f"Ref {r.get('imovel_ref', '?')}",
            r.get("natureza", ""),
            f"T{r['quartos']}" if r.get("quartos") is not None else "",
            f"{r['area_util']}m²" if r.get("area_util") else "",
            preco,
            r.get("freguesia") or r.get("concelho", ""),
        ]
        linhas.append(" | ".join(p for p in partes if p))
        if r.get("descricao"):
            linhas.append(f"  {r['descricao'][:120]}")

    return "\n".join(linhas)


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
        lead_existente = (
            supabase.table("agente_leads")
            .select("id")
            .eq("cliente_id", cliente_id)
            .not_.in_("estado", ["fechado", "perdido"])
            .limit(1)
            .execute()
        )
        if not lead_existente.data:
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
                    if block.get("type") != "tool_use":
                        continue

                    loop = asyncio.get_event_loop()

                    if block["name"] == "pesquisar_imoveis":
                        try:
                            resultado = await loop.run_in_executor(
                                None, _pesquisar_imoveis, block.get("input", {})
                            )
                            tool_result_content = resultado
                        except Exception:
                            logger.exception("Erro ao pesquisar imóveis para %s", from_number)
                            tool_result_content = "Erro ao pesquisar imóveis."

                    elif block["name"] == "guardar_dados_cliente":
                        dados = block.get("input", {})
                        try:
                            await loop.run_in_executor(None, _save_to_db, dados, from_number)
                            dados_guardados = True
                            tool_result_content = "Dados guardados com sucesso."
                        except Exception:
                            logger.exception("Erro ao guardar dados WhatsApp de %s", from_number)
                            tool_result_content = "Erro ao guardar dados."

                    else:
                        tool_result_content = "Tool desconhecida."

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
