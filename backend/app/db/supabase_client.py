from supabase import create_client, Client
from app.config import settings

_client: Client | None = None
_auth_client: Client | None = None


def get_supabase() -> Client:
    """Projecto unificado — todas as tabelas de dados (clientes, leads,
    chamadas, conversas, config, tarefas, imoveis)."""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_imoveis_url, settings.supabase_imoveis_key)
    return _client


def get_supabase_auth() -> Client:
    """Projecto principal — só para validar tokens de login (Supabase Auth).
    As contas de utilizador ficam lá; os dados não."""
    global _auth_client
    if _auth_client is None:
        _auth_client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _auth_client
