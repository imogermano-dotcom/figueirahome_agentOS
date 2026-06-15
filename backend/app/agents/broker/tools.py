import asyncio
import logging
from datetime import datetime

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "name": "consultar_clientes",
        "description": "Consulta clientes na base de dados com filtros opcionais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Filtrar por nome (parcial)"},
                "telefone": {"type": "string", "description": "Filtrar por telefone (exacto)"},
                "tipo_interesse": {
                    "type": "string",
                    "enum": ["compra", "arrendamento", "venda", "outro"],
                    "description": "Tipo de interesse do cliente",
                },
                "zona_preferida": {"type": "string", "description": "Zona/localização preferida (parcial)"},
                "criado_depois": {"type": "string", "description": "Data ISO 8601 — só clientes criados depois desta data"},
            },
        },
    },
    {
        "name": "consultar_imoveis",
        "description": "Consulta imóveis na base de dados com filtros opcionais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "description": "Tipo de imóvel (ex: moradia, apartamento)"},
                "localizacao": {"type": "string", "description": "Localização/zona (parcial)"},
                "preco_max": {"type": "number", "description": "Preço máximo em euros"},
                "preco_min": {"type": "number", "description": "Preço mínimo em euros"},
                "estado": {
                    "type": "string",
                    "enum": ["disponivel", "vendido", "arrendado", "reservado"],
                },
                "fonte": {"type": "string", "description": "Origem do imóvel (manual, csv, agente_voz, etc.)"},
            },
        },
    },
    {
        "name": "consultar_leads",
        "description": "Consulta leads (oportunidades de negócio) na base de dados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "estado": {
                    "type": "string",
                    "enum": ["novo", "contactado", "qualificado", "proposta", "fechado", "perdido"],
                },
                "cliente_id": {"type": "string", "description": "UUID do cliente"},
                "criado_depois": {"type": "string", "description": "Data ISO 8601"},
            },
        },
    },
]


async def consultar_clientes(filtros: dict) -> list[dict]:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _query():
        q = supabase.table("agente_clientes").select("*")
        if filtros.get("nome"):
            q = q.ilike("nome", f"%{filtros['nome']}%")
        if filtros.get("telefone"):
            q = q.eq("telefone", filtros["telefone"])
        if filtros.get("tipo_interesse"):
            q = q.eq("tipo_interesse", filtros["tipo_interesse"])
        if filtros.get("zona_preferida"):
            q = q.ilike("zona_preferida", f"%{filtros['zona_preferida']}%")
        if filtros.get("criado_depois"):
            q = q.gte("criado_em", filtros["criado_depois"])
        return q.order("criado_em", desc=True).limit(20).execute()

    resp = await loop.run_in_executor(None, _query)
    return resp.data or []


async def consultar_imoveis(filtros: dict) -> list[dict]:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _query():
        q = supabase.table("agente_imoveis").select("*")
        if filtros.get("tipo"):
            q = q.ilike("tipo", f"%{filtros['tipo']}%")
        if filtros.get("localizacao"):
            q = q.ilike("localizacao", f"%{filtros['localizacao']}%")
        if filtros.get("preco_max") is not None:
            q = q.lte("preco", filtros["preco_max"])
        if filtros.get("preco_min") is not None:
            q = q.gte("preco", filtros["preco_min"])
        if filtros.get("estado"):
            q = q.eq("estado", filtros["estado"])
        if filtros.get("fonte"):
            q = q.eq("fonte", filtros["fonte"])
        return q.order("criado_em", desc=True).limit(20).execute()

    resp = await loop.run_in_executor(None, _query)
    return resp.data or []


async def consultar_leads(filtros: dict) -> list[dict]:
    supabase = get_supabase()
    loop = asyncio.get_event_loop()

    def _query():
        q = supabase.table("agente_leads").select("*, agente_clientes(nome, telefone)")
        if filtros.get("estado"):
            q = q.eq("estado", filtros["estado"])
        if filtros.get("cliente_id"):
            q = q.eq("cliente_id", filtros["cliente_id"])
        if filtros.get("criado_depois"):
            q = q.gte("criado_em", filtros["criado_depois"])
        return q.order("criado_em", desc=True).limit(20).execute()

    resp = await loop.run_in_executor(None, _query)
    return resp.data or []


async def execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "consultar_clientes":
            result = await consultar_clientes(inputs)
        elif name == "consultar_imoveis":
            result = await consultar_imoveis(inputs)
        elif name == "consultar_leads":
            result = await consultar_leads(inputs)
        else:
            return f"Tool desconhecida: {name}"

        if not result:
            return "Nenhum resultado encontrado."
        return str(result)
    except Exception:
        logger.exception("Erro a executar tool %s", name)
        return "Erro ao consultar a base de dados."
