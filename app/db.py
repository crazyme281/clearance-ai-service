from functools import lru_cache
from supabase import create_client, Client
from app import config


@lru_cache
def get_service_client() -> Client:
    """
    Service-role client. Bypasses RLS. Used ONLY inside app/tools/, and only
    ever queried with IDs that were resolved from a verified user token —
    never with an ID an LLM invented or a caller passed unchecked.
    """
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache
def get_anon_client() -> Client:
    """Anon-role client, used only to verify incoming user JWTs."""
    return create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
