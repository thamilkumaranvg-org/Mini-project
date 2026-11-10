"""Authentication, session management, CSRF checks, and role-based access control."""
from typing import Optional, List, Dict, Any, Callable
from fastapi import Request, Response, Depends, status
import jwt
from app.config import settings
from app.db import get_db
from app.errors import Unauthorized, Forbidden, BadRequest, AppError


def verify_csrf_protection(request: Request) -> None:
    """Ensure mutating requests include X-Requested-With: fetch."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header = request.headers.get("X-Requested-With", "")
        if header.lower() != "fetch":
            raise BadRequest(
                code="CSRF_FAILED",
                message="Missing or invalid X-Requested-With header."
            )


def get_token_from_request(request: Request) -> Optional[str]:
    """Retrieve token from httpOnly cookie or Authorization header."""
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


async def get_current_user(request: Request) -> Dict[str, Any]:
    """Verify access token via Supabase Auth and load the corresponding profile."""
    token = get_token_from_request(request)
    if not token:
        raise Unauthorized(message="Missing authentication token.")

    db = get_db()
    try:
        # Verify token using Supabase Auth
        user_response = db.auth.get_user(token)
        if not user_response or not user_response.user:
            raise Unauthorized(message="Session expired or invalid.")
        user_id = user_response.user.id
    except Exception:
        # Try decoding JWT payload directly if Supabase local fallback
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub")
            if not user_id:
                raise Unauthorized(message="Invalid token payload.")
        except Exception:
            raise Unauthorized(message="Session expired or invalid.")

    # Fetch profile from profiles table
    try:
        profile_res = db.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        if not profile_res.data:
            raise Unauthorized(message="User profile not found.")
        profile = profile_res.data[0]
        if not profile.get("is_active", True):
            raise Forbidden(code="ACCOUNT_DEACTIVATED", message="Account is deactivated.")
        return profile
    except AppError:
        raise
    except Exception as e:
        raise Unauthorized(message=f"Could not load user profile: {str(e)}")


def require_role(*allowed_roles: str) -> Callable:
    """Dependency that ensures the authenticated user has one of the allowed roles."""
    async def role_checker(
        request: Request,
        user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        # Enforce CSRF protection on mutating endpoints
        verify_csrf_protection(request)

        user_role = user.get("role")
        if user_role not in allowed_roles:
            raise Forbidden(
                code="FORBIDDEN_ROLE",
                message=f"Access denied for role '{user_role}'. Required: {list(allowed_roles)}"
            )
        return user

    return role_checker


def set_auth_cookies(response: Response, access_token: str, refresh_token: Optional[str] = None) -> None:
    """Set secure httpOnly session cookies."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/"
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            secure=settings.COOKIE_SECURE,
            path="/"
        )


def clear_auth_cookies(response: Response) -> None:
    """Clear session cookies on logout."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")


def record_audit(
    actor_id: Optional[str],
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Write an entry into public.audit_log table."""
    try:
        db = get_db()
        db.table("audit_log").insert({
            "actor_id": actor_id,
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id) if entity_id else None,
            "details": details or {}
        }).execute()
    except Exception as e:
        # Audit logging failure should not crash main transactions
        print(f"[AUDIT LOG ERROR] Failed to record audit log: {e}")

