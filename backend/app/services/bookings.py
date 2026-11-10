"""Booking creation, receipt formatting, and cancellation service."""
import secrets
import string
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional
from app.config import settings
from app.clock import now_ist, today_ist
from app.db import get_db
from app.errors import BadRequest, parse_db_exception, NotFound, Forbidden
from app.services.qr import generate_opaque_qr_token, generate_qr_data_uri
from app.services.sessions import parse_time_str, format_time_display
from app.services.notifications import create_notification
from app.security import record_audit
from app.schemas import BookingReceiptResponse


def generate_receipt_no(session_date: date, session_id: int) -> str:
    """Format: SB-YYYYMMDD-S<session>-<4 random uppercase alphanumerics>."""
    date_str = session_date.strftime("%Y%m%d")
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(4))
    return f"SB-{date_str}-S{session_id}-{suffix}"


def create_customer_booking(customer_profile: Dict[str, Any], session_date: date, session_id: int, crop_id: int, quantity_kg: float) -> BookingReceiptResponse:
    """Create a new booking by executing atomic fn_book_slot."""
    current_dt = now_ist()
    curr_today = today_ist()

    # 1. Validate date within window
    max_date = curr_today + timedelta(days=settings.BOOKING_WINDOW_DAYS - 1)
    if session_date < curr_today or session_date > max_date:
        raise BadRequest("INVALID_DATE", f"Booking date must be between {curr_today} and {max_date}.")

    # 2. Validate quantity
    if quantity_kg <= 0 or quantity_kg > settings.MAX_QUANTITY_KG:
        raise BadRequest("INVALID_QUANTITY", f"Quantity must be between 0.01 and {settings.MAX_QUANTITY_KG} kg.")

    db = get_db()

    # 3. Fetch session template
    tmpl_res = db.table("session_templates").select("*").eq("id", session_id).limit(1).execute()
    if not tmpl_res.data:
        raise BadRequest("INVALID_SESSION", "Selected session does not exist.")
    tmpl = tmpl_res.data[0]

    # 4. Check if session has already ended if booking for today
    if session_date == curr_today:
        end_t = parse_time_str(tmpl["end_time"])
        s_end_dt = datetime.combine(session_date, end_t, tzinfo=current_dt.tzinfo)
        s_cutoff_dt = s_end_dt - timedelta(minutes=settings.BOOKING_CLOSE_MINUTES_BEFORE_END)
        if current_dt > s_cutoff_dt:
            raise BadRequest("SESSION_ENDED", "Booking is closed for this session.")

    # 5. Generate identifiers
    receipt_no = generate_receipt_no(session_date, session_id)
    qr_token = generate_opaque_qr_token()
    receipt_name = customer_profile["full_name"]
    customer_id = customer_profile["id"]

    # 6. Call database RPC
    try:
        rpc_res = db.rpc("fn_book_slot", {
            "p_customer_id": customer_id,
            "p_session_date": session_date.isoformat(),
            "p_session_id": session_id,
            "p_crop_id": crop_id,
            "p_quantity_kg": round(quantity_kg, 2),
            "p_receipt_name": receipt_name,
            "p_receipt_no": receipt_no,
            "p_qr_token": qr_token
        }).execute()
        booking_data = rpc_res.data
    except Exception as e:
        raise parse_db_exception(e)

    # 7. Create notification & send email
    first_name = receipt_name.split()[0]
    create_notification(
        user_id=customer_id,
        user_email=customer_profile["email"],
        first_name=first_name,
        notification_type="booking_confirmed",
        title="Slot Booking Confirmed",
        message=f"Your produce selling slot for {tmpl['name']} on {session_date.strftime('%d-%b-%Y')} is confirmed.",
        booking_id=booking_data["id"],
        meta={
            "receipt_no": receipt_no,
            "session_info": f"{tmpl['name']} ({format_time_display(parse_time_str(tmpl['start_time']))} - {format_time_display(parse_time_str(tmpl['end_time']))})",
            "date_str": session_date.strftime("%d-%b-%Y"),
            "extra_info": f"Crop: {booking_data['crop_name']} | Declared Qty: {booking_data['quantity_kg']} kg | Est. Amount: ₹{booking_data['estimated_amount']}"
        }
    )

    record_audit(
        actor_id=customer_id,
        action="CREATE_BOOKING",
        entity="bookings",
        entity_id=booking_data["id"],
        details={"receipt_no": receipt_no, "session_date": str(session_date), "session_id": session_id}
    )

    return format_booking_receipt(booking_data, tmpl, is_owner=True)


def format_booking_receipt(booking: Dict[str, Any], tmpl: Optional[Dict[str, Any]] = None, is_owner: bool = True) -> BookingReceiptResponse:
    """Format booking record into public receipt view enforcing R6 and R7."""
    current_dt = now_ist()
    session_date = date.fromisoformat(str(booking["session_date"]))
    status = booking["status"]

    if tmpl is None:
        db = get_db()
        tmpl_res = db.table("session_templates").select("*").eq("id", booking["session_id"]).limit(1).execute()
        tmpl = tmpl_res.data[0] if tmpl_res.data else {"name": f"Session {booking['session_id']}", "start_time": "09:00", "end_time": "11:00"}

    start_t = parse_time_str(tmpl["start_time"])
    end_t = parse_time_str(tmpl["end_time"])
    s_start_dt = datetime.combine(session_date, start_t, tzinfo=current_dt.tzinfo)
    s_end_dt = datetime.combine(session_date, end_t, tzinfo=current_dt.tzinfo)

    is_expired = (current_dt > s_end_dt) and (status in ("booked", "missed"))
    can_cancel = (status == "booked") and (current_dt < s_start_dt)

    # R7: QR image returned ONLY to owning customer when status == 'booked' and session not ended
    qr_png = None
    if is_owner and status == "booked" and not is_expired:
        qr_png = generate_qr_data_uri(booking["qr_token"])

    validity_text = f"Valid only for {session_date.strftime('%d-%b-%Y')} between {format_time_display(start_t)} and {format_time_display(end_t)}"

    return BookingReceiptResponse(
        id=str(booking["id"]),
        receipt_no=booking["receipt_no"],
        receipt_name=booking["receipt_name"],
        session_date=session_date,
        session_id=int(booking["session_id"]),
        session_name=tmpl["name"],
        start_time=format_time_display(start_t),
        end_time=format_time_display(end_t),
        crop_id=int(booking.get("crop_id") or 0),
        crop_name=booking["crop_name"],
        declared_quantity_kg=float(booking["quantity_kg"]),
        price_per_kg=float(booking["price_per_kg"]),
        estimated_amount=float(booking["estimated_amount"]),
        status=status,
        queue_number=booking.get("queue_number"),
        checked_in_at=booking.get("checked_in_at"),
        called_at=booking.get("called_at"),
        verified_quantity_kg=booking.get("verified_quantity_kg"),
        final_amount=booking.get("final_amount"),
        payout_status=booking.get("payout_status", "pending"),
        completed_at=booking.get("completed_at"),
        cancelled_at=booking.get("cancelled_at"),
        created_at=booking.get("created_at") or current_dt,
        qr_png_data_uri=qr_png,
        validity_text=validity_text,
        is_expired=is_expired,
        can_cancel=can_cancel
    )


def cancel_booking(customer_id: str, booking_id: str) -> BookingReceiptResponse:
    """Cancel booking if in booked status before session start."""
    db = get_db()
    current_dt = now_ist()
    try:
        rpc_res = db.rpc("fn_cancel_booking", {
            "p_booking_id": booking_id,
            "p_customer_id": customer_id,
            "p_now": current_dt.isoformat()
        }).execute()
        updated_booking = rpc_res.data
    except Exception as e:
        raise parse_db_exception(e)

    record_audit(
        actor_id=customer_id,
        action="CANCEL_BOOKING",
        entity="bookings",
        entity_id=booking_id
    )

    return format_booking_receipt(updated_booking, is_owner=True)

