from supabase import create_client, Client
from app.config import settings

_client: Client | None = None
_imoveis_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def get_supabase_imoveis() -> Client:
    global _imoveis_client
    if _imoveis_client is None:
        _imoveis_client = create_client(settings.supabase_imoveis_url, settings.supabase_imoveis_key)
    return _imoveis_client
