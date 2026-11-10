"""Check-in scan verification, FIFO queue sequencing, officer desk operations."""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.config import settings
from app.clock import now_ist, today_ist
from app.db import get_db
from app.errors import BadRequest, parse_db_exception, NotFound, Forbidden, AppError
from app.services.notifications import create_notification
from app.security import record_audit
from app.services.sessions import parse_time_str, format_time_display
from app.schemas import (
    ScanSuccessResponse,
    ScannerQueueItemResponse,
    ScannerCurrentSessionResponse,
    OfficerSessionSummary,
    OfficerTomorrowSessionSummary,
    OfficerQueueItem,
    OfficerCalledBookingResponse,
    OfficerCalledProfile,
    OfficerCompletedRecord
)


# ======================================================================
# SCANNER SERVICE LOGIC
# ======================================================================

def process_scanner_checkin(scanner_profile: Dict[str, Any], qr_token: str) -> ScanSuccessResponse:
    """Process gate check-in via atomic fn_check_in."""
    db = get_db()
    current_dt = now_ist()
    scanner_id = scanner_profile["id"]

    try:
        rpc_res = db.rpc("fn_check_in", {
            "p_qr_token": qr_token.strip(),
            "p_scanner_id": scanner_id,
            "p_now": current_dt.isoformat(),
            "p_open_minutes": settings.CHECKIN_OPEN_MINUTES_BEFORE
        }).execute()
        booking = rpc_res.data
    except Exception as e:
        raise parse_db_exception(e)

    # Fetch template name for receipt response
    tmpl_res = db.table("session_templates").select("name").eq("id", booking["session_id"]).limit(1).execute()
    session_name = tmpl_res.data[0]["name"] if tmpl_res.data else f"Session {booking['session_id']}"

    # Notify customer of successful gate check-in and queue assignment
    cust_res = db.table("profiles").select("email, full_name").eq("id", booking["customer_id"]).limit(1).execute()
    if cust_res.data:
        cust = cust_res.data[0]
        first_name = cust["full_name"].split()[0]
        create_notification(
            user_id=booking["customer_id"],
            user_email=cust["email"],
            first_name=first_name,
            notification_type="checked_in",
            title=f"Checked In - Queue #{booking['queue_number']}",
            message=f"You are checked in for {session_name}. Your queue position is #{booking['queue_number']}.",
            booking_id=booking["id"],
            meta={
                "receipt_no": booking["receipt_no"],
                "session_info": session_name,
                "extra_info": f"Queue Position: #{booking['queue_number']}"
            }
        )

    record_audit(
        actor_id=scanner_id,
        action="SCAN_CHECK_IN",
        entity="bookings",
        entity_id=booking["id"],
        details={"queue_number": booking["queue_number"], "session_id": booking["session_id"]}
    )

    return ScanSuccessResponse(
        success=True,
        receipt_no=booking["receipt_no"],
        receipt_name=booking["receipt_name"],
        session_name=session_name,
        queue_number=booking["queue_number"],
        checked_in_at=booking["checked_in_at"]
    )


def get_scanner_current_session() -> ScannerCurrentSessionResponse:
    """Identify today's current or upcoming session for the scanner."""
    db = get_db()
    current_dt = now_ist()
    curr_date_str = today_ist().isoformat()

    tmpls_res = db.table("session_templates").select("*").order("id").execute()
    tmpls = tmpls_res.data or []

    active_tmpl = None
    for tmpl in tmpls:
        start_t = parse_time_str(tmpl["start_time"])
        end_t = parse_time_str(tmpl["end_time"])
        s_start = datetime.combine(today_ist(), start_t, tzinfo=current_dt.tzinfo)
        s_end = datetime.combine(today_ist(), end_t, tzinfo=current_dt.tzinfo)
        if current_dt <= s_end:
            active_tmpl = tmpl
            break

    if not active_tmpl and tmpls:
        active_tmpl = tmpls[-1]

    s_id = active_tmpl["id"]
    bookings_res = db.table("bookings").select("status").eq("session_date", curr_date_str).eq("session_id", s_id).neq("status", "cancelled").execute()
    rows = bookings_res.data or []

    total_booked = len(rows)
    checked_in = sum(1 for r in rows if r["status"] in ("checked_in", "called", "completed"))
    waiting = sum(1 for r in rows if r["status"] == "checked_in")

    start_t = parse_time_str(active_tmpl["start_time"])
    end_t = parse_time_str(active_tmpl["end_time"])
    s_start = datetime.combine(today_ist(), start_t, tzinfo=current_dt.tzinfo)
    s_end = datetime.combine(today_ist(), end_t, tzinfo=current_dt.tzinfo)
    is_active_now = (s_start <= current_dt <= s_end)

    return ScannerCurrentSessionResponse(
        session_id=s_id,
        session_name=active_tmpl["name"],
        start_time=format_time_display(start_t),
        end_time=format_time_display(end_t),
        is_active_now=is_active_now,
        total_booked=total_booked,
        checked_in_count=checked_in,
        waiting_count=waiting
    )


def get_scanner_queue(session_id: int) -> List[ScannerQueueItemResponse]:
    """Return live checked-in queue for today's session (R8: receipt name, queue #, check-in time ONLY)."""
    db = get_db()
    curr_date_str = today_ist().isoformat()

    res = db.table("bookings")\
        .select("queue_number, receipt_name, checked_in_at")\
        .eq("session_date", curr_date_str)\
        .eq("session_id", session_id)\
        .in_("status", ["checked_in", "called", "completed"])\
        .order("queue_number")\
        .execute()

    items = []
    for r in (res.data or []):
        if r.get("queue_number"):
            items.append(ScannerQueueItemResponse(
                queue_number=r["queue_number"],
                receipt_name=r["receipt_name"],
                checked_in_at=r["checked_in_at"]
            ))
    return items


# ======================================================================
# OFFICER SERVICE LOGIC (STRICT PRIVACY ENFORCEMENT - R9 & R10)
# ======================================================================

def get_officer_today_sessions() -> List[OfficerSessionSummary]:
    """Retrieve session counts and statuses for today."""
    db = get_db()
    current_dt = now_ist()
    curr_date_str = today_ist().isoformat()

    tmpls_res = db.table("session_templates").select("*").order("id").execute()
    tmpls = tmpls_res.data or []

    bookings_res = db.table("bookings").select("session_id, status").eq("session_date", curr_date_str).neq("status", "cancelled").execute()
    bookings = bookings_res.data or []

    summaries = []
    for tmpl in tmpls:
        s_id = tmpl["id"]
        capacity = tmpl["capacity"]
        s_rows = [b for b in bookings if b["session_id"] == s_id]

        booked = len(s_rows)
        checked_in = sum(1 for b in s_rows if b["status"] in ("checked_in", "called", "completed"))
        waiting = sum(1 for b in s_rows if b["status"] == "checked_in")
        serving = sum(1 for b in s_rows if b["status"] == "called")
        completed = sum(1 for b in s_rows if b["status"] == "completed")
        no_show = sum(1 for b in s_rows if b["status"] == "no_show")
        remaining = max(0, capacity - booked)

        start_t = parse_time_str(tmpl["start_time"])
        end_t = parse_time_str(tmpl["end_time"])
        s_start = datetime.combine(today_ist(), start_t, tzinfo=current_dt.tzinfo)
        s_end = datetime.combine(today_ist(), end_t, tzinfo=current_dt.tzinfo)

        if current_dt < s_start:
            s_status = "upcoming"
        elif current_dt <= s_end:
            s_status = "in_progress"
        else:
            s_status = "ended"

        summaries.append(OfficerSessionSummary(
            session_id=s_id,
            session_name=tmpl["name"],
            start_time=format_time_display(start_t),
            end_time=format_time_display(end_t),
            capacity=capacity,
            booked_count=booked,
            checked_in_count=checked_in,
            waiting_count=waiting,
            serving_count=serving,
            completed_count=completed,
            no_show_count=no_show,
            remaining_seats=remaining,
            session_status=s_status
        ))

    return summaries


def get_officer_tomorrow_sessions() -> List[OfficerTomorrowSessionSummary]:
    """Retrieve session booked counts and remaining capacity for tomorrow."""
    db = get_db()
    tomorrow_date = today_ist() + timedelta(days=1)
    tomorrow_date_str = tomorrow_date.isoformat()

    tmpls_res = db.table("session_templates").select("*").order("id").execute()
    tmpls = tmpls_res.data or []

    bookings_res = db.table("bookings")\
        .select("session_id, status")\
        .eq("session_date", tomorrow_date_str)\
        .neq("status", "cancelled")\
        .execute()
    bookings = bookings_res.data or []

    summaries = []
    for tmpl in tmpls:
        s_id = tmpl["id"]
        capacity = tmpl["capacity"]
        s_rows = [b for b in bookings if b["session_id"] == s_id]
        booked = len(s_rows)
        remaining = max(0, capacity - booked)

        start_t = parse_time_str(tmpl["start_time"])
        end_t = parse_time_str(tmpl["end_time"])

        status_lbl = "Full" if remaining == 0 else ("Almost full" if remaining <= 2 else "Available")

        summaries.append(OfficerTomorrowSessionSummary(
            session_id=s_id,
            session_name=tmpl["name"],
            session_date=tomorrow_date_str,
            start_time=format_time_display(start_t),
            end_time=format_time_display(end_t),
            capacity=capacity,
            booked_count=booked,
            remaining_seats=remaining,
            status_label=status_lbl
        ))

    return summaries


def get_officer_waiting_queue(session_id: int) -> List[OfficerQueueItem]:
    """R9: Officer sees only queue_number + receipt_name + checked_in_at for waiting farmers."""
    db = get_db()
    curr_date_str = today_ist().isoformat()

    res = db.table("bookings")\
        .select("queue_number, receipt_name, checked_in_at")\
        .eq("session_date", curr_date_str)\
        .eq("session_id", session_id)\
        .eq("status", "checked_in")\
        .order("queue_number")\
        .execute()

    return [
        OfficerQueueItem(
            queue_number=r["queue_number"],
            receipt_name=r["receipt_name"],
            checked_in_at=r["checked_in_at"]
        ) for r in (res.data or [])
    ]


def officer_call_next(officer_profile: Dict[str, Any], session_id: int) -> OfficerCalledBookingResponse:
    """Call next waiting farmer in FIFO order using atomic fn_call_next."""
    db = get_db()
    current_dt = now_ist()
    curr_date_str = today_ist().isoformat()
    officer_id = officer_profile["id"]

    try:
        rpc_res = db.rpc("fn_call_next", {
            "p_officer_id": officer_id,
            "p_session_date": curr_date_str,
            "p_session_id": session_id,
            "p_now": current_dt.isoformat()
        }).execute()
        booking = rpc_res.data
    except Exception as e:
        raise parse_db_exception(e)

    # Fetch customer profile (authorized now that status is 'called')
    cust_res = db.table("profiles").select("*").eq("id", booking["customer_id"]).limit(1).execute()
    if not cust_res.data:
        raise NotFound("CUSTOMER_NOT_FOUND", "Customer profile could not be loaded.")
    cust = cust_res.data[0]

    # Fetch session name
    tmpl_res = db.table("session_templates").select("name").eq("id", session_id).limit(1).execute()
    session_name = tmpl_res.data[0]["name"] if tmpl_res.data else f"Session {session_id}"

    # Notify customer that they are being called to the desk
    first_name = cust["full_name"].split()[0]
    create_notification(
        user_id=booking["customer_id"],
        user_email=cust["email"],
        first_name=first_name,
        notification_type="called",
        title="Counter Calling: Please proceed to desk",
        message=f"Queue #{booking['queue_number']}, please proceed to Officer Counter for produce verification.",
        booking_id=booking["id"],
        meta={
            "receipt_no": booking["receipt_no"],
            "session_info": session_name,
            "extra_info": f"Queue Position #{booking['queue_number']} - Counter Called"
        }
    )

    record_audit(
        actor_id=officer_id,
        action="CALL_CUSTOMER",
        entity="bookings",
        entity_id=booking["id"],
        details={"queue_number": booking["queue_number"], "session_id": session_id}
    )

    return OfficerCalledBookingResponse(
        booking_id=str(booking["id"]),
        receipt_no=booking["receipt_no"],
        queue_number=booking["queue_number"],
        session_name=session_name,
        crop_name=booking["crop_name"],
        declared_quantity_kg=float(booking["quantity_kg"]),
        price_per_kg=float(booking["price_per_kg"]),
        estimated_amount=float(booking["estimated_amount"]),
        called_at=booking["called_at"],
        profile=OfficerCalledProfile(
            full_name=cust["full_name"],
            dob=cust.get("dob"),
            gender=cust.get("gender"),
            state=cust.get("state"),
            district=cust.get("district"),
            address=cust.get("address"),
            mobile=cust.get("mobile")
        )
    )


def get_officer_current_called(officer_profile: Dict[str, Any]) -> Optional[OfficerCalledBookingResponse]:
    """Retrieve currently called customer profile for this officer (R9)."""
    db = get_db()
    officer_id = officer_profile["id"]

    res = db.table("bookings")\
        .select("*")\
        .eq("called_by", officer_id)\
        .eq("status", "called")\
        .limit(1)\
        .execute()

    if not res.data:
        return None

    booking = res.data[0]
    cust_res = db.table("profiles").select("*").eq("id", booking["customer_id"]).limit(1).execute()
    cust = cust_res.data[0] if cust_res.data else {}

    tmpl_res = db.table("session_templates").select("name").eq("id", booking["session_id"]).limit(1).execute()
    session_name = tmpl_res.data[0]["name"] if tmpl_res.data else f"Session {booking['session_id']}"

    return OfficerCalledBookingResponse(
        booking_id=str(booking["id"]),
        receipt_no=booking["receipt_no"],
        queue_number=booking["queue_number"],
        session_name=session_name,
        crop_name=booking["crop_name"],
        declared_quantity_kg=float(booking["quantity_kg"]),
        price_per_kg=float(booking["price_per_kg"]),
        estimated_amount=float(booking["estimated_amount"]),
        called_at=booking["called_at"],
        profile=OfficerCalledProfile(
            full_name=cust.get("full_name", booking["receipt_name"]),
            dob=cust.get("dob"),
            gender=cust.get("gender"),
            state=cust.get("state"),
            district=cust.get("district"),
            address=cust.get("address"),
            mobile=cust.get("mobile")
        )
    )


def officer_complete_booking(officer_profile: Dict[str, Any], booking_id: str, verified_qty: float) -> OfficerCompletedRecord:
    """Verify produce weight, compute final amount, and mark completed/paid."""
    db = get_db()
    current_dt = now_ist()
    officer_id = officer_profile["id"]

    try:
        rpc_res = db.rpc("fn_complete_booking", {
            "p_booking_id": booking_id,
            "p_officer_id": officer_id,
            "p_verified_qty": round(verified_qty, 2),
            "p_now": current_dt.isoformat()
        }).execute()
        booking = rpc_res.data
    except Exception as e:
        raise parse_db_exception(e)

    # Notify customer of final payout
    cust_res = db.table("profiles").select("email, full_name").eq("id", booking["customer_id"]).limit(1).execute()
    if cust_res.data:
        cust = cust_res.data[0]
        first_name = cust["full_name"].split()[0]
        create_notification(
            user_id=booking["customer_id"],
            user_email=cust["email"],
            first_name=first_name,
            notification_type="completed",
            title="Produce Sold & Cash Paid",
            message=f"Verification complete: {booking['verified_quantity_kg']} kg verified. Final cash payment of ₹{booking['final_amount']} settled.",
            booking_id=booking["id"],
            meta={
                "receipt_no": booking["receipt_no"],
                "extra_info": f"Verified: {booking['verified_quantity_kg']} kg | Paid in Cash: ₹{booking['final_amount']}"
            }
        )

    record_audit(
        actor_id=officer_id,
        action="COMPLETE_BOOKING",
        entity="bookings",
        entity_id=booking_id,
        details={"verified_qty": booking["verified_quantity_kg"], "final_amount": booking["final_amount"]}
    )

    return OfficerCompletedRecord(
        booking_id=str(booking["id"]),
        receipt_no=booking["receipt_no"],
        receipt_name=booking["receipt_name"],
        crop_name=booking["crop_name"],
        declared_quantity_kg=float(booking["quantity_kg"]),
        verified_quantity_kg=float(booking["verified_quantity_kg"]),
        price_per_kg=float(booking["price_per_kg"]),
        final_amount=float(booking["final_amount"]),
        completed_at=booking["completed_at"]
    )


def officer_mark_no_show(officer_profile: Dict[str, Any], booking_id: str) -> None:
    """Mark called customer as no-show."""
    db = get_db()
    current_dt = now_ist()
    officer_id = officer_profile["id"]

    try:
        db.rpc("fn_mark_no_show", {
            "p_booking_id": booking_id,
            "p_officer_id": officer_id,
            "p_now": current_dt.isoformat()
        }).execute()
    except Exception as e:
        raise parse_db_exception(e)

    record_audit(
        actor_id=officer_id,
        action="MARK_NO_SHOW",
        entity="bookings",
        entity_id=booking_id
    )


def get_officer_completed_today(officer_profile: Dict[str, Any]) -> List[OfficerCompletedRecord]:
    """Retrieve receipt-level records of customers completed today (R9: receipt data only, no profile)."""
    db = get_db()
    curr_date_str = today_ist().isoformat()

    res = db.table("bookings")\
        .select("id, receipt_no, receipt_name, crop_name, quantity_kg, verified_quantity_kg, price_per_kg, final_amount, completed_at")\
        .eq("session_date", curr_date_str)\
        .eq("status", "completed")\
        .order("completed_at", desc=True)\
        .execute()

    return [
        OfficerCompletedRecord(
            booking_id=str(r["id"]),
            receipt_no=r["receipt_no"],
            receipt_name=r["receipt_name"],
            crop_name=r["crop_name"],
            declared_quantity_kg=float(r["quantity_kg"]),
            verified_quantity_kg=float(r["verified_quantity_kg"] or r["quantity_kg"]),
            price_per_kg=float(r["price_per_kg"]),
            final_amount=float(r["final_amount"] or 0.0),
            completed_at=r["completed_at"]
        ) for r in (res.data or [])
    ]

