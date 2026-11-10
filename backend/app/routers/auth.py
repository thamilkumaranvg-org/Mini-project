"""Authentication routes: registration, multi-portal login, session refresh, logout."""
from typing import Dict, Any
from fastapi import APIRouter, Depends, Response, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings
from app.db import get_db, get_auth_client
from app.errors import BadRequest, Unauthorized, Forbidden
from app.security import (
    set_auth_cookies,
    clear_auth_cookies,
    get_current_user,
    record_audit,
    verify_csrf_protection
)
from app.schemas import (
    RegisterCustomerRequest,
    LoginRequest,
    UserProfileResponse
)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def register_customer(payload: RegisterCustomerRequest, request: Request):
    """Register a new farmer account."""
    verify_csrf_protection(request)
    db = get_db()

    # Check for existing email or mobile in profiles
    existing_email = db.table("profiles").select("id").eq("email", payload.email.lower()).execute()
    if existing_email.data:
        raise BadRequest("EMAIL_EXISTS", "A user with this email address already exists.")

    existing_mobile = db.table("profiles").select("id").eq("mobile", payload.mobile).execute()
    if existing_mobile.data:
        raise BadRequest("MOBILE_EXISTS", "A user with this mobile number already exists.")

    # 1. Create auth user in Supabase Auth via admin API
    auth_user_id = None
    try:
        auth_res = db.auth.admin.create_user({
            "email": payload.email.lower(),
            "password": payload.password,
            "email_confirm": True,
            "user_metadata": {"full_name": payload.full_name}
        })
        if not auth_res.user:
            raise BadRequest("AUTH_CREATE_FAILED", "Failed to create user credentials.")
        auth_user_id = auth_res.user.id
    except Exception as e:
        raise BadRequest("REGISTRATION_FAILED", f"Could not create user account: {str(e)}")

    # 2. Insert into public.profiles
    try:
        db.table("profiles").insert({
            "id": auth_user_id,
            "role": "customer",
            "full_name": payload.full_name.strip(),
            "email": payload.email.lower(),
            "mobile": payload.mobile,
            "dob": payload.dob.isoformat(),
            "gender": payload.gender,
            "state": payload.state.strip(),
            "district": payload.district.strip(),
            "address": payload.address.strip(),
            "is_active": True
        }).execute()
    except Exception as e:
        # Avoid orphaned auth users
        if auth_user_id:
            try:
                db.auth.admin.delete_user(auth_user_id)
            except Exception:
                pass
        raise BadRequest("PROFILE_CREATE_FAILED", f"Failed to save profile details: {str(e)}")

    record_audit(
        actor_id=auth_user_id,
        action="REGISTER",
        entity="profiles",
        entity_id=auth_user_id,
        details={"role": "customer", "email": payload.email.lower()}
    )

    return {"message": "Registration successful. You can now log in.", "user_id": auth_user_id}


@router.post("/login")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(payload: LoginRequest, request: Request, response: Response):
    """Authenticate user with portal-role verification and set httpOnly cookies."""
    verify_csrf_protection(request)
    auth_client = get_auth_client()
    db = get_db()

    try:
        # Sign in with Supabase Auth using isolated auth client
        sign_in_res = auth_client.auth.sign_in_with_password({
            "email": payload.email.lower(),
            "password": payload.password
        })
    except Exception:
        raise Unauthorized("INVALID_CREDENTIALS", "Invalid email or password.")

    if not sign_in_res.user or not sign_in_res.session:
        raise Unauthorized("INVALID_CREDENTIALS", "Invalid email or password.")

    user_id = sign_in_res.user.id

    # Load profile to verify portal matching and active status
    profile_res = db.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if not profile_res.data:
        raise Unauthorized("INVALID_CREDENTIALS", "Invalid email or password.")

    profile = profile_res.data[0]

    # Verify role matches the requested portal
    if profile.get("role") != payload.portal:
        raise Unauthorized("INVALID_CREDENTIALS", "Invalid email or password for this portal.")

    if not profile.get("is_active", True):
        raise Forbidden("ACCOUNT_INACTIVE", "Your account has been deactivated. Please contact support.")

    # Set httpOnly cookies
    set_auth_cookies(
        response=response,
        access_token=sign_in_res.session.access_token,
        refresh_token=sign_in_res.session.refresh_token
    )

    # Log staff logins into audit log
    if profile.get("role") in ("scanner", "officer", "admin"):
        record_audit(
            actor_id=user_id,
            action="STAFF_LOGIN",
            entity="profiles",
            entity_id=user_id,
            details={"portal": payload.portal}
        )

    return {
        "message": "Login successful",
        "user": {
            "id": profile["id"],
            "role": profile["role"],
            "full_name": profile["full_name"],
            "email": profile["email"]
        }
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Clear session cookies."""
    verify_csrf_protection(request)
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    """Refresh access token using refresh_token cookie."""
    verify_csrf_protection(request)
    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        raise Unauthorized("NO_REFRESH_TOKEN", "Missing refresh token.")

    auth_client = get_auth_client()
    try:
        refreshed = auth_client.auth.refresh_session(refresh_tok)
        if not refreshed.session:
            raise Unauthorized("REFRESH_FAILED", "Failed to refresh session.")

        set_auth_cookies(
            response=response,
            access_token=refreshed.session.access_token,
            refresh_token=refreshed.session.refresh_token
        )
        return {"message": "Token refreshed successfully"}
    except Exception:
        clear_auth_cookies(response)
        raise Unauthorized("REFRESH_FAILED", "Session expired. Please log in again.")


@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    """Return currently authenticated user profile."""
    return UserProfileResponse(
        id=user["id"],
        role=user["role"],
        full_name=user["full_name"],
        email=user["email"],
        mobile=user.get("mobile"),
        dob=user.get("dob"),
        gender=user.get("gender"),
        state=user.get("state"),
        district=user.get("district"),
        address=user.get("address"),
        is_active=user["is_active"],
        created_at=user["created_at"]
    )
