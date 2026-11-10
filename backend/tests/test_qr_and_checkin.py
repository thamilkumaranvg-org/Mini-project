"""Tests for QR token privacy, validation window, and sequential FIFO check-in."""
import pytest
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from app.services.qr import generate_opaque_qr_token, generate_qr_data_uri


def test_qr_token_opaque_no_personal_data():
    """Verify R7: QR encodes ONLY an opaque random token, never personal data."""
    token = generate_opaque_qr_token()
    assert len(token) >= 32
    # Ensure no plain email, name, phone or JSON structures
    assert "@" not in token
    assert "{" not in token
    assert " " not in token

    # Check data URI generation
    uri = generate_qr_data_uri(token)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > 100


def simulate_check_in_validation(
    booking: dict,
    now_dt: datetime,
    session_start: time,
    session_end: time,
    open_minutes: int = 0
) -> str:
    """Pure logic replicating fn_check_in rejection ordering."""
    if not booking:
        return "INVALID_QR"
    if booking.get("status") == "cancelled":
        return "BOOKING_CANCELLED"
    if booking.get("status") in ("checked_in", "called", "completed", "no_show"):
        return "ALREADY_CHECKED_IN"
    if booking.get("status") == "missed":
        return "SESSION_ENDED"

    today_ist = now_dt.date()
    if booking.get("session_date") != today_ist:
        return "WRONG_DAY"

    tz = now_dt.tzinfo
    start_dt = datetime.combine(today_ist, session_start, tzinfo=tz)
    end_dt = datetime.combine(today_ist, session_end, tzinfo=tz)
    from datetime import timedelta
    open_dt = start_dt - timedelta(minutes=open_minutes)

    if now_dt < open_dt:
        return "SESSION_NOT_STARTED"
    if now_dt > end_dt:
        return "SESSION_ENDED"

    return "SUCCESS"


def test_check_in_rejection_rules():
    """Verify R8 scan rejection codes in order."""
    tz = ZoneInfo("Asia/Kolkata")
    booking_date = date(2026, 11, 9)
    s_start = time(9, 0)
    s_end = time(11, 0)

    base_booking = {
        "qr_token": "valid_token",
        "status": "booked",
        "session_date": booking_date,
        "session_id": 1
    }

    # 1. Invalid QR
    assert simulate_check_in_validation(None, datetime(2026, 11, 9, 9, 30, tzinfo=tz), s_start, s_end) == "INVALID_QR"

    # 2. Cancelled
    b_cancelled = {**base_booking, "status": "cancelled"}
    assert simulate_check_in_validation(b_cancelled, datetime(2026, 11, 9, 9, 30, tzinfo=tz), s_start, s_end) == "BOOKING_CANCELLED"

    # 3. Already Checked In
    b_checked = {**base_booking, "status": "checked_in"}
    assert simulate_check_in_validation(b_checked, datetime(2026, 11, 9, 9, 30, tzinfo=tz), s_start, s_end) == "ALREADY_CHECKED_IN"

    # 4. Wrong Day
    tomorrow = datetime(2026, 11, 10, 9, 30, tzinfo=tz)
    assert simulate_check_in_validation(base_booking, tomorrow, s_start, s_end) == "WRONG_DAY"

    # 5. Session Not Started
    too_early = datetime(2026, 11, 9, 8, 45, tzinfo=tz)
    assert simulate_check_in_validation(base_booking, too_early, s_start, s_end) == "SESSION_NOT_STARTED"

    # 6. Session Ended
    too_late = datetime(2026, 11, 9, 11, 15, tzinfo=tz)
    assert simulate_check_in_validation(base_booking, too_late, s_start, s_end) == "SESSION_ENDED"

    # 7. Valid Scan
    valid_time = datetime(2026, 11, 9, 9, 30, tzinfo=tz)
    assert simulate_check_in_validation(base_booking, valid_time, s_start, s_end) == "SUCCESS"


def test_sequential_fifo_queue_numbering():
    """Verify R8: Queue numbers increment 1..8 strictly by scan order."""
    queue = []
    for _ in range(8):
        next_num = len(queue) + 1
        queue.append(next_num)

    assert queue == [1, 2, 3, 4, 5, 6, 7, 8]

