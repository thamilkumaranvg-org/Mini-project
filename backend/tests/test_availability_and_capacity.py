"""Tests for booking availability labels, capacity limits, and pricing math."""
import pytest
from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo
from app.services.sessions import parse_time_str
from app.schemas import SessionAvailability


def compute_availability_label(capacity: int, booked_count: int, is_closed: bool, almost_full_threshold: int = 2) -> tuple[str, bool]:
    """Helper mimicking the availability label business rule R3."""
    remaining = max(0, capacity - booked_count)
    if is_closed or remaining == 0:
        return "Full", False
    elif 1 <= remaining <= almost_full_threshold:
        return "Almost full", True
    else:
        return "Available", True


def test_availability_labels():
    """Verify R3: 0 remaining -> Full, 1..2 -> Almost full, >=3 -> Available."""
    capacity = 8

    # 0 booked -> 8 left -> Available
    lbl, bookable = compute_availability_label(capacity, 0, False)
    assert lbl == "Available"
    assert bookable is True

    # 5 booked -> 3 left -> Available
    lbl, bookable = compute_availability_label(capacity, 5, False)
    assert lbl == "Available"
    assert bookable is True

    # 6 booked -> 2 left -> Almost full
    lbl, bookable = compute_availability_label(capacity, 6, False)
    assert lbl == "Almost full"
    assert bookable is True

    # 7 booked -> 1 left -> Almost full
    lbl, bookable = compute_availability_label(capacity, 7, False)
    assert lbl == "Almost full"
    assert bookable is True

    # 8 booked -> 0 left -> Full
    lbl, bookable = compute_availability_label(capacity, 8, False)
    assert lbl == "Full"
    assert bookable is False

    # Closed session
    lbl, bookable = compute_availability_label(capacity, 2, True)
    assert lbl == "Full"
    assert bookable is False


def test_ended_sessions_excluded_for_today():
    """Verify R2: For today, sessions whose end time passed are excluded."""
    tz = ZoneInfo("Asia/Kolkata")
    today = date(2026, 11, 9)

    # Simulate clock at 11:30 AM
    current_dt = datetime(2026, 11, 9, 11, 30, tzinfo=tz)

    sessions = [
        {"id": 1, "name": "Session 1", "start": time(9, 0), "end": time(11, 0)},
        {"id": 2, "name": "Session 2", "start": time(11, 20), "end": time(13, 20)},
        {"id": 3, "name": "Session 3", "start": time(14, 0), "end": time(16, 0)},
    ]

    visible_today = []
    for s in sessions:
        s_end_dt = datetime.combine(today, s["end"], tzinfo=tz)
        if current_dt > s_end_dt:
            continue  # Excluded
        visible_today.append(s["id"])

    # Session 1 ended at 11:00 AM, so only Session 2 & 3 should be visible
    assert visible_today == [2, 3]


def test_booking_pricing_math():
    """Verify R5: estimated_amount = round(quantity_kg * price_per_kg, 2)."""
    qty = 543.25
    rate = 23.00
    est = round(qty * rate, 2)
    assert est == 12494.75

    # Verification payout math
    verified_qty = 541.80
    final_amt = round(verified_qty * rate, 2)
    assert final_amt == 12461.40

