"""Session timing, window calculations, and availability service."""
from datetime import date, datetime, timedelta, time
from typing import List, Dict, Any, Optional
from app.config import settings
from app.clock import now_ist, today_ist
from app.db import get_db
from app.schemas import DayAvailabilityResponse, SessionAvailability


def parse_time_str(val: Any) -> time:
    """Parse time string or time object into datetime.time."""
    if isinstance(val, time):
        return val
    s = str(val).strip()
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)


def format_time_display(t: time) -> str:
    """Format time into HH:MM display."""
    return t.strftime("%H:%M")


def run_lazy_expiry() -> None:
    """Trigger DB-level expiry function to keep active statuses clean."""
    if "placeholder" in settings.SUPABASE_URL or settings.APP_ENV == "test":
        return
    try:
        db = get_db()
        now_dt = now_ist().isoformat()
        db.rpc("fn_expire_bookings", {"p_now": now_dt}).execute()
    except Exception:
        # Silently fail in lazy mode if DB offline or RPC not installed yet
        pass


def get_weekly_availability() -> List[DayAvailabilityResponse]:
    """Retrieve slot availability for today through today + (BOOKING_WINDOW_DAYS - 1)."""
    run_lazy_expiry()
    db = get_db()

    start_date = today_ist()
    end_date = start_date + timedelta(days=settings.BOOKING_WINDOW_DAYS - 1)
    current_dt = now_ist()

    # Fetch all session templates
    templates_res = db.table("session_templates").select("*").order("id").execute()
    templates = templates_res.data or []

    # Fetch booking counts using fn_availability RPC or direct table query
    try:
        avail_res = db.rpc("fn_availability", {
            "p_from": start_date.isoformat(),
            "p_to": end_date.isoformat()
        }).execute()
        counts_data = avail_res.data or []
    except Exception:
        # Fallback to direct query if RPC is not yet registered
        b_res = db.table("bookings").select("session_date, session_id, status").gte("session_date", start_date.isoformat()).lte("session_date", end_date.isoformat()).neq("status", "cancelled").execute()
        counts_dict: Dict[tuple, int] = {}
        for r in (b_res.data or []):
            key = (r["session_date"], r["session_id"])
            counts_dict[key] = counts_dict.get(key, 0) + 1
        counts_data = [{"session_date": k[0], "session_id": k[1], "booked_count": v} for k, v in counts_dict.items()]

    counts_map: Dict[tuple, int] = {}
    for row in counts_data:
        counts_map[(str(row["session_date"]), int(row["session_id"]))] = int(row["booked_count"])

    day_responses: List[DayAvailabilityResponse] = []

    for d_offset in range(settings.BOOKING_WINDOW_DAYS):
        target_date = start_date + timedelta(days=d_offset)
        target_date_str = target_date.isoformat()
        is_today = (target_date == start_date)

        session_list: List[SessionAvailability] = []

        for tmpl in templates:
            s_id = int(tmpl["id"])
            start_t = parse_time_str(tmpl["start_time"])
            end_t = parse_time_str(tmpl["end_time"])
            capacity = int(tmpl["capacity"])

            # Compute session boundary timestamps in Asia/Kolkata
            s_end_dt = datetime.combine(target_date, end_t, tzinfo=current_dt.tzinfo)
            s_cutoff_dt = s_end_dt - timedelta(minutes=settings.BOOKING_CLOSE_MINUTES_BEFORE_END)

            # R2: For today, sessions whose end time has passed are excluded from the availability response
            if is_today and current_dt > s_end_dt:
                continue

            # Check if booking is still open
            is_closed = (current_dt > s_cutoff_dt) if is_today else False

            booked = counts_map.get((target_date_str, s_id), 0)
            remaining = max(0, capacity - booked)

            # R3: Availability labels
            if is_closed or remaining == 0:
                status_label = "Full"
                is_bookable = False
            elif 1 <= remaining <= settings.ALMOST_FULL_THRESHOLD:
                status_label = "Almost full"
                is_bookable = True
            else:
                status_label = "Available"
                is_bookable = True

            session_list.append(SessionAvailability(
                session_id=s_id,
                name=tmpl["name"],
                start_time=format_time_display(start_t),
                end_time=format_time_display(end_t),
                capacity=capacity,
                booked_count=booked,
                remaining_seats=remaining,
                status_label=status_label,
                is_bookable=is_bookable
            ))

        day_responses.append(DayAvailabilityResponse(
            date=target_date,
            is_today=is_today,
            sessions=session_list
        ))

    return day_responses
