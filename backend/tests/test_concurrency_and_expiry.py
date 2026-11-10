"""Tests for atomic capacity locking, concurrency simulation, and expiration logic."""
import pytest
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import threading


def test_capacity_8_limit_and_rejection():
    """Verify R4: 9th booking for a session is rejected when capacity is 8."""
    capacity = 8
    bookings = []

    def book_slot(customer_id: str):
        # Atomic lock simulation
        active_count = len([b for b in bookings if b["status"] != "cancelled"])
        if active_count >= capacity:
            raise ValueError("SESSION_FULL")
        if any(b["customer_id"] == customer_id and b["status"] in ("booked", "checked_in", "called", "completed") for b in bookings):
            raise ValueError("ALREADY_BOOKED")
        b = {"id": f"b_{len(bookings)+1}", "customer_id": customer_id, "status": "booked"}
        bookings.append(b)
        return b

    # Fill 8 slots
    for i in range(8):
        book_slot(f"cust_{i+1}")
    assert len(bookings) == 8

    # 9th attempt must be rejected with SESSION_FULL
    with pytest.raises(ValueError) as exc_info:
        book_slot("cust_9")
    assert "SESSION_FULL" in str(exc_info.value)

    # Cancel one booking -> frees seat
    bookings[0]["status"] = "cancelled"
    # Now cust_9 can book
    new_b = book_slot("cust_9")
    assert new_b["customer_id"] == "cust_9"


def test_duplicate_active_booking_rejected():
    """Verify R4: One active booking per customer per date+session."""
    bookings = [{"customer_id": "cust_1", "status": "booked"}]

    def check_duplicate(customer_id: str):
        if any(b["customer_id"] == customer_id and b["status"] in ("booked", "checked_in", "called", "completed") for b in bookings):
            raise ValueError("ALREADY_BOOKED")

    with pytest.raises(ValueError) as exc:
        check_duplicate("cust_1")
    assert "ALREADY_BOOKED" in str(exc.value)

    # If first booking was cancelled, customer can book again
    bookings[0]["status"] = "cancelled"
    check_duplicate("cust_1")  # Should not raise


def test_concurrent_last_seat_competition():
    """Verify race condition prevention: 8 parallel requests for 1 remaining seat yield exactly ONE success."""
    capacity = 8
    # Start with 7 existing bookings, leaving exactly 1 seat
    bookings = [{"id": f"b_{i}", "customer_id": f"c_{i}", "status": "booked"} for i in range(7)]
    lock = threading.Lock()

    success_list = []
    failed_list = []

    def attempt_booking(cust_id: str):
        # Simulates pg_advisory_xact_lock
        with lock:
            active_count = len([b for b in bookings if b["status"] != "cancelled"])
            if active_count >= capacity:
                failed_list.append((cust_id, "SESSION_FULL"))
                return
            b = {"id": f"b_new_{cust_id}", "customer_id": cust_id, "status": "booked"}
            bookings.append(b)
            success_list.append(cust_id)

    threads = [threading.Thread(target=attempt_booking, args=(f"competitor_{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 1 competitor succeeds, 7 fail
    assert len(success_list) == 1
    assert len(failed_list) == 7
    assert len(bookings) == 8


def test_expiration_logic():
    """Verify R12: unscanned 'booked' become 'missed' after session end, past-day checked-in become 'no_show'."""
    tz = ZoneInfo("Asia/Kolkata")
    now_dt = datetime(2026, 11, 9, 11, 15, tzinfo=tz)  # Session 1 ended at 11:00 AM
    today = now_dt.date()

    bookings = [
        # Session 1 booked (unscanned) -> should become missed
        {"id": "b1", "session_date": today, "session_id": 1, "end_time": time(11, 0), "status": "booked"},
        # Session 1 checked_in -> stays checked_in (queue drains)
        {"id": "b2", "session_date": today, "session_id": 1, "end_time": time(11, 0), "status": "checked_in"},
        # Session 2 booked (ends at 13:20) -> stays booked
        {"id": "b3", "session_date": today, "session_id": 2, "end_time": time(13, 20), "status": "booked"},
        # Past-day item left checked_in -> becomes no_show
        {"id": "b4", "session_date": today - timedelta(days=1), "session_id": 1, "end_time": time(11, 0), "status": "checked_in"},
    ]

    expired_results = []
    for b in bookings:
        s_end_dt = datetime.combine(b["session_date"], b["end_time"], tzinfo=tz)
        if b["status"] == "booked" and s_end_dt < now_dt:
            b["status"] = "missed"
            expired_results.append((b["id"], "missed"))
        elif b["status"] in ("checked_in", "called") and b["session_date"] < today:
            b["status"] = "no_show"
            expired_results.append((b["id"], "no_show"))

    assert ("b1", "missed") in expired_results
    assert ("b4", "no_show") in expired_results
    # b2 (checked_in today) remains checked_in to be served
    assert next(x for x in bookings if x["id"] == "b2")["status"] == "checked_in"
    # b3 (future session) remains booked
    assert next(x for x in bookings if x["id"] == "b3")["status"] == "booked"

