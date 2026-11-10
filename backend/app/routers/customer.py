"""Customer (Farmer) routes: slots availability, bookings, receipts, notifications, profile."""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request
from app.db import get_db
from app.security import require_role
from app.errors import BadRequest, NotFound, Forbidden
from app.services.sessions import get_weekly_availability
from app.services.pricing import get_active_crops
from app.services.bookings import create_customer_booking, format_booking_receipt, cancel_booking
from app.schemas import (
    DayAvailabilityResponse,
    CropResponse,
    CreateBookingRequest,
    BookingReceiptResponse,
    BookingSummaryResponse,
    UpdateProfileRequest,
    UserProfileResponse,
    NotificationResponse
)

router = APIRouter(prefix="/api", tags=["customer"])


@router.get("/availability", response_model=List[DayAvailabilityResponse])
async def get_availability(user: Dict[str, Any] = Depends(require_role("customer", "admin"))):
    """Retrieve 7-day slot availability."""
    return get_weekly_availability()


@router.get("/crops", response_model=List[CropResponse])
async def get_crops(user: Dict[str, Any] = Depends(require_role("customer", "admin", "officer"))):
    """Retrieve active crop catalog with MSP prices."""
    return get_active_crops()


@router.post("/bookings", response_model=BookingReceiptResponse)
async def create_booking(payload: CreateBookingRequest, user: Dict[str, Any] = Depends(require_role("customer"))):
    """Book a produce selling slot."""
    return create_customer_booking(
        customer_profile=user,
        session_date=payload.session_date,
        session_id=payload.session_id,
        crop_id=payload.crop_id,
        quantity_kg=payload.quantity_kg
    )


@router.get("/bookings", response_model=List[BookingSummaryResponse])
async def get_customer_bookings(user: Dict[str, Any] = Depends(require_role("customer"))):
    """Get customer's booking history (newest first)."""
    db = get_db()
    res = db.table("bookings")\
        .select("id, receipt_no, session_date, session_id, crop_name, quantity_kg, estimated_amount, status, queue_number, final_amount, payout_status, created_at")\
        .eq("customer_id", user["id"])\
        .order("created_at", desc=True)\
        .execute()

    tmpls_res = db.table("session_templates").select("id, name, start_time, end_time").execute()
    tmpls_map = {t["id"]: t for t in (tmpls_res.data or [])}

    summaries = []
    for r in (res.data or []):
        t = tmpls_map.get(r["session_id"], {"name": f"Session {r['session_id']}", "start_time": "09:00", "end_time": "11:00"})
        summaries.append(BookingSummaryResponse(
            id=str(r["id"]),
            receipt_no=r["receipt_no"],
            session_date=r["session_date"],
            session_id=r["session_id"],
            session_name=t["name"],
            start_time=t["start_time"][:5],
            end_time=t["end_time"][:5],
            crop_name=r["crop_name"],
            declared_quantity_kg=float(r["quantity_kg"]),
            estimated_amount=float(r["estimated_amount"]),
            status=r["status"],
            queue_number=r.get("queue_number"),
            final_amount=float(r["final_amount"]) if r.get("final_amount") is not None else None,
            payout_status=r.get("payout_status", "pending"),
            created_at=r["created_at"]
        ))
    return summaries


@router.get("/bookings/{booking_id}", response_model=BookingReceiptResponse)
async def get_booking_receipt(booking_id: str, user: Dict[str, Any] = Depends(require_role("customer", "admin"))):
    """Get detailed receipt with QR image (QR returned only to owner while active)."""
    db = get_db()
    res = db.table("bookings").select("*").eq("id", booking_id).limit(1).execute()
    if not res.data:
        raise NotFound("BOOKING_NOT_FOUND", "Booking not found.")

    booking = res.data[0]
    # Check ownership unless admin
    if user["role"] == "customer" and booking["customer_id"] != user["id"]:
        raise Forbidden("FORBIDDEN", "You do not own this booking.")

    return format_booking_receipt(booking, is_owner=(user["id"] == booking["customer_id"]))


@router.post("/bookings/{booking_id}/cancel", response_model=BookingReceiptResponse)
async def cancel_customer_booking(booking_id: str, user: Dict[str, Any] = Depends(require_role("customer"))):
    """Cancel a booking before session start."""
    return cancel_booking(customer_id=user["id"], booking_id=booking_id)


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user: Dict[str, Any] = Depends(require_role("customer"))):
    """Retrieve profile of logged in customer."""
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


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(payload: UpdateProfileRequest, user: Dict[str, Any] = Depends(require_role("customer"))):
    """Update profile fields (role and email cannot be changed)."""
    db = get_db()
    updates: Dict[str, Any] = {}

    if payload.full_name is not None:
        updates["full_name"] = payload.full_name.strip()
    if payload.mobile is not None:
        # Check uniqueness if changed
        if payload.mobile != user.get("mobile"):
            exist = db.table("profiles").select("id").eq("mobile", payload.mobile).neq("id", user["id"]).execute()
            if exist.data:
                raise BadRequest("MOBILE_EXISTS", "This mobile number is already registered.")
            updates["mobile"] = payload.mobile
    if payload.dob is not None:
        updates["dob"] = payload.dob.isoformat()
    if payload.gender is not None:
        updates["gender"] = payload.gender
    if payload.state is not None:
        updates["state"] = payload.state.strip()
    if payload.district is not None:
        updates["district"] = payload.district.strip()
    if payload.address is not None:
        updates["address"] = payload.address.strip()

    if updates:
        res = db.table("profiles").update(updates).eq("id", user["id"]).execute()
        updated_profile = res.data[0]
    else:
        updated_profile = user

    return UserProfileResponse(
        id=updated_profile["id"],
        role=updated_profile["role"],
        full_name=updated_profile["full_name"],
        email=updated_profile["email"],
        mobile=updated_profile.get("mobile"),
        dob=updated_profile.get("dob"),
        gender=updated_profile.get("gender"),
        state=updated_profile.get("state"),
        district=updated_profile.get("district"),
        address=updated_profile.get("address"),
        is_active=updated_profile["is_active"],
        created_at=updated_profile["created_at"]
    )


# ======================================================================
# NOTIFICATIONS
# ======================================================================

@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(user: Dict[str, Any] = Depends(require_role("customer"))):
    """Retrieve in-app notifications for customer."""
    db = get_db()
    res = db.table("notifications")\
        .select("id, type, title, message, is_read, created_at, booking_id")\
        .eq("user_id", user["id"])\
        .order("created_at", desc=True)\
        .limit(50)\
        .execute()

    return [
        NotificationResponse(
            id=str(r["id"]),
            type=r["type"],
            title=r["title"],
            message=r["message"],
            is_read=r["is_read"],
            created_at=r["created_at"],
            booking_id=str(r["booking_id"]) if r.get("booking_id") else None
        ) for r in (res.data or [])
    ]


@router.get("/notifications/unread-count")
async def get_unread_count(user: Dict[str, Any] = Depends(require_role("customer"))):
    """Return count of unread notifications."""
    db = get_db()
    res = db.table("notifications").select("id", count="exact").eq("user_id", user["id"]).eq("is_read", False).execute()
    return {"unread_count": res.count or len(res.data or [])}


@router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, user: Dict[str, Any] = Depends(require_role("customer"))):
    """Mark a notification as read."""
    db = get_db()
    db.table("notifications").update({"is_read": True}).eq("id", notif_id).eq("user_id", user["id"]).execute()
    return {"message": "Notification marked as read"}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(user: Dict[str, Any] = Depends(require_role("customer"))):
    """Mark all notifications as read."""
    db = get_db()
    db.table("notifications").update({"is_read": True}).eq("user_id", user["id"]).eq("is_read", False).execute()
    return {"message": "All notifications marked as read"}

