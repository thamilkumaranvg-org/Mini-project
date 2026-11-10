"""Test clock service, timezone handling, and dev override behavior."""
import os
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from app.clock import now_ist, today_ist, KOLKATA_TZ


def test_now_ist_timezone():
    """Verify now_ist returns datetime in Asia/Kolkata."""
    dt = now_ist()
    assert dt.tzinfo is not None
    assert str(dt.tzinfo) == "Asia/Kolkata" or dt.tzinfo == KOLKATA_TZ


def test_time_override_in_development():
    """Verify TIME_OVERRIDE_ISO works when APP_ENV is development."""
    os.environ["APP_ENV"] = "development"
    os.environ["TIME_OVERRIDE_ISO"] = "2026-11-15T10:30:00+05:30"

    dt = now_ist()
    assert dt.year == 2026
    assert dt.month == 11
    assert dt.day == 15
    assert dt.hour == 10
    assert dt.minute == 30
    assert today_ist() == date(2026, 11, 15)

    # Clean up override
    os.environ["TIME_OVERRIDE_ISO"] = ""
    os.environ["APP_ENV"] = "test"


def test_time_override_ignored_in_production():
    """Verify TIME_OVERRIDE_ISO is strictly ignored when APP_ENV is production."""
    os.environ["APP_ENV"] = "production"
    os.environ["TIME_OVERRIDE_ISO"] = "2026-11-15T10:30:00+05:30"

    dt = now_ist()
    real_today = datetime.now(KOLKATA_TZ).date()
    # In production, the mock year/month/day should not apply
    assert dt.date() == real_today

    # Reset
    os.environ["TIME_OVERRIDE_ISO"] = ""
    os.environ["APP_ENV"] = "test"

