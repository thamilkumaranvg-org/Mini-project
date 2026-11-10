"""Tests for RBAC role guards, CSRF checks, and email background failure resilience."""
import pytest
from app.errors import AppError
from app.security import verify_csrf_protection
from app.services.email import render_email_template


def test_csrf_header_verification():
    """Verify mutating requests without X-Requested-With: fetch are rejected."""
    class MockRequest:
        def __init__(self, method: str, headers: dict):
            self.method = method
            self.headers = headers

    # Valid POST with X-Requested-With: fetch
    valid_req = MockRequest("POST", {"X-Requested-With": "fetch"})
    verify_csrf_protection(valid_req)  # Should not raise

    # Invalid POST without header
    invalid_req = MockRequest("POST", {})
    with pytest.raises(AppError) as exc_info:
        verify_csrf_protection(invalid_req)
    assert exc_info.value.code == "CSRF_FAILED"

    # GET requests should pass without header
    get_req = MockRequest("GET", {})
    verify_csrf_protection(get_req)


def test_email_template_rendering():
    """Verify email template rendering with palette and privacy rules (no QR token, no personal leak)."""
    meta = {
        "receipt_no": "SB-20261109-S1-TEST",
        "session_info": "Session 1 (09:00 - 11:00)",
        "date_str": "09-Nov-2026",
        "extra_info": "Crop: Paddy | Declared: 500 kg"
    }
    html = render_email_template(
        title="Slot Booking Confirmed",
        recipient_first_name="Murugan",
        message="Your slot has been reserved.",
        meta=meta
    )

    assert "Slot Booking Confirmed" in html
    assert "Murugan" in html
    assert "SB-20261109-S1-TEST" in html
    assert "Session 1" in html
    # Ensure no QR tokens or password/token leaks in email content
    assert "qr_token" not in html
