"""In-app notifications and email dispatch orchestration."""
from typing import Optional, Dict, Any
import asyncio
from app.db import get_db
from app.services.email import send_email_async


async def _deliver_email_task(
    notification_id: str,
    user_email: str,
    subject: str,
    title: str,
    first_name: str,
    message: str,
    meta: Dict[str, Any]
) -> None:
    """Background delivery task updating notification record with result."""
    success, error_msg = await send_email_async(
        to_email=user_email,
        subject=subject,
        title=title,
        recipient_first_name=first_name,
        message=message,
        meta=meta
    )
    try:
        db = get_db()
        db.table("notifications").update({
            "email_status": "sent" if success else "failed",
            "email_error": error_msg
        }).eq("id", notification_id).execute()
    except Exception as e:
        print(f"[NOTIFICATION ERROR] Failed to update email delivery status: {e}")


def create_notification(
    user_id: str,
    user_email: str,
    first_name: str,
    notification_type: str,
    title: str,
    message: str,
    booking_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """Create in-app notification row and trigger background email."""
    db = get_db()
    res = db.table("notifications").insert({
        "user_id": user_id,
        "booking_id": booking_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "is_read": False,
        "email_status": "pending"
    }).execute()

    notification_id = res.data[0]["id"] if res.data else None

    # Spawn background email task
    if notification_id and user_email:
        asyncio.create_task(
            _deliver_email_task(
                notification_id=notification_id,
                user_email=user_email,
                subject=f"Farmer Slot Booking: {title}",
                title=title,
                first_name=first_name,
                message=message,
                meta=meta or {}
            )
        )

    return notification_id

