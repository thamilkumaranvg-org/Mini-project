"""Clock service enforcing Asia/Kolkata timezone with development override support."""
from datetime import datetime
import os
from zoneinfo import ZoneInfo
from dateutil import parser

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Return current datetime in Asia/Kolkata timezone.
    
    If APP_ENV != 'production' and TIME_OVERRIDE_ISO is provided, returns
    the overridden datetime converted to Asia/Kolkata.
    """
    app_env = os.getenv("APP_ENV", "development").lower()
    override_iso = os.getenv("TIME_OVERRIDE_ISO", "").strip()

    if app_env != "production" and override_iso:
        try:
            dt = parser.isoparse(override_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KOLKATA_TZ)
            else:
                dt = dt.astimezone(KOLKATA_TZ)
            return dt
        except Exception:
            pass

    return datetime.now(KOLKATA_TZ)


def today_ist() -> datetime.date:
    """Return today's date in Asia/Kolkata."""
    return now_ist().date()

