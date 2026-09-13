from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_supabase() -> Client:
    """Cliente único — um só projecto Supabase desde 13/09 (o de Auth,
    `fykbo...`, foi eliminado e integrado neste). Antes disto havia dois
    clientes (`get_supabase()` para dados, `get_supabase_auth()` só para
    login) porque eram dois projectos; agora seria uma distinção sem
    diferença."""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_secret_key)
    return _client
