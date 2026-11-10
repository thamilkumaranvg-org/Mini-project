"""Supabase Client initialization and database helper utilities using service role."""
from typing import Optional
import httpx
from supabase import create_client, Client, ClientOptions
from app.config import settings

_supabase_client: Optional[Client] = None
_auth_client: Optional[Client] = None


def get_db() -> Client:
    """Return singleton Supabase client authenticated with service role key.
    Always ensures postgrest headers use the service role key to bypass RLS.
    """
    global _supabase_client
    if _supabase_client is None:
        opts = ClientOptions(postgrest_client_timeout=5)
        _supabase_client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
            options=opts
        )
    # Guarantee postgrest client always operates as service role
    _supabase_client.postgrest.auth(settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_client


def get_auth_client() -> Client:
    """Return a dedicated client for user auth operations (sign in, session refresh).
    Using an anon-key client prevents user sessions from mutating the service-role client.
    """
    global _auth_client
    if _auth_client is None:
        opts = ClientOptions(postgrest_client_timeout=5)
        _auth_client = create_client(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_ANON_KEY,
            options=opts
        )
    return _auth_client


def check_db_health() -> bool:
    """Test connectivity by querying session_templates with short timeout."""
    if "placeholder" in settings.SUPABASE_URL or settings.APP_ENV == "test":
        return False
    try:
        # Quick HTTP probe to avoid blocking
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{settings.SUPABASE_URL}/rest/v1/", headers={
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
            })
            return r.status_code in (200, 404, 401)
    except Exception:
        return False
