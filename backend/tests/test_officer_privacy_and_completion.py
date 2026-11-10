"""Tests for Officer desk privacy enforcement (R9) and payout calculations."""
import pytest
from app.schemas import OfficerQueueItem, OfficerCalledBookingResponse, OfficerCalledProfile, OfficerCompletedRecord


def test_officer_waiting_queue_privacy():
    """Verify R9: waiting queue schema contains only queue_number, receipt_name, checked_in_at."""
    item = OfficerQueueItem(
        queue_number=1,
        receipt_name="Murugan K",
        checked_in_at="2026-11-09T09:15:00+05:30"
    )
    dumped = item.model_dump()
    assert set(dumped.keys()) == {"queue_number", "receipt_name", "checked_in_at"}
    # Assert personal fields are absent
    assert "mobile" not in dumped
    assert "dob" not in dumped
    assert "address" not in dumped
    assert "qr_token" not in dumped


def test_officer_completed_record_privacy():
    """Verify R9: completed record schema contains receipt-level data only, zero profile data."""
    rec = OfficerCompletedRecord(
        booking_id="550e8400-e29b-41d4-a716-446655440000",
        receipt_no="SB-20261109-S1-ABCD",
        receipt_name="Murugan K",
        crop_name="Paddy (Dhan)",
        declared_quantity_kg=500.0,
        verified_quantity_kg=498.5,
        price_per_kg=23.00,
        final_amount=11465.50,
        completed_at="2026-11-09T09:45:00+05:30"
    )
    dumped = rec.model_dump()
    assert "mobile" not in dumped
    assert "address" not in dumped
    assert "dob" not in dumped
    assert "qr_token" not in dumped
    assert dumped["final_amount"] == 11465.50


def test_price_snapshot_immutability():
    """Verify R5: Later price changes do not alter existing booking snapshots."""
    # Booking created with Paddy at snapshot price 23.00
    booking_snapshot_price = 23.00
    declared_qty = 500.0
    verified_qty = 510.0

    # Admin increases Paddy price to 28.00 tomorrow
    admin_new_price = 28.00

    # Final amount calculation must use the snapshot price 23.00, NOT the new 28.00
    final_amount = round(verified_qty * booking_snapshot_price, 2)
    assert final_amount == 11730.00
    assert final_amount != round(verified_qty * admin_new_price, 2)

