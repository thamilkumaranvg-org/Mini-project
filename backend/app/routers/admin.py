"""Admin routes: dashboard, bookings manager with CSV export, crops catalog, staff management, audit log."""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, date
import csv
import io
from fastapi import APIRouter, Depends, Query, Response, status
from app.db import get_db
from app.clock import now_ist, today_ist
from app.config import settings
from app.security import require_role, record_audit
from app.errors import BadRequest, NotFound
from app.services.pricing import get_all_crops_admin, create_crop, update_crop
from app.services.sessions import parse_time_str, format_time_display
from app.schemas import (
    AdminDashboardResponse,
    AdminSessionMetric,
    AdminDashboardTotals,
    AdminCropItem,
    CreateCropRequest,
    UpdateCropRequest,
    CreateStaffRequest,
    UpdateStaffStatusRequest,
    AuditLogItem
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ======================================================================
# DASHBOARD
# ======================================================================

@router.get("/dashboard", response_model=AdminDashboardResponse)
async def get_dashboard(user: Dict[str, Any] = Depends(require_role("admin"))):
    """Admin live dashboard metrics across today, current session, and next 7 days."""
    db = get_db()
    current_dt = now_ist()
    curr_date_str = today_ist().isoformat()

    tmpls_res = db.table("session_templates").select("*").order("id").execute()
    tmpls = tmpls_res.data or []

    # Today's bookings
    today_b_res = db.table("bookings").select("*").eq("session_date", curr_date_str).neq("status", "cancelled").execute()
    today_bookings = today_b_res.data or []

    today_metrics: List[AdminSessionMetric] = []
    current_metric: Optional[AdminSessionMetric] = None

    for tmpl in tmpls:
        s_id = tmpl["id"]
        capacity = tmpl["capacity"]
        s_rows = [b for b in today_bookings if b["session_id"] == s_id]

        booked = len(s_rows)
        checked_in = sum(1 for b in s_rows if b["status"] in ("checked_in", "called", "completed"))
        waiting = sum(1 for b in s_rows if b["status"] == "checked_in")
        serving = sum(1 for b in s_rows if b["status"] == "called")
        completed = sum(1 for b in s_rows if b["status"] == "completed")
        no_shows = sum(1 for b in s_rows if b["status"] == "no_show")
        seats_remaining = max(0, capacity - booked)

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

        m = AdminSessionMetric(
            session_id=s_id,
            name=tmpl["name"],
            timing=f"{format_time_display(start_t)} - {format_time_display(end_t)}",
            status=s_status,
            capacity=capacity,
            booked=booked,
            checked_in=checked_in,
            waiting=waiting,
            serving=serving,
            completed=completed,
            no_shows=no_shows,
            seats_remaining=seats_remaining
        )
        today_metrics.append(m)

        if s_status == "in_progress" or (current_metric is None and s_status == "upcoming"):
            current_metric = m

    if current_metric is None and today_metrics:
        current_metric = today_metrics[-1]

    # Totals today
    completed_rows = [b for b in today_bookings if b["status"] == "completed"]
    customers_served = len(completed_rows)
    total_kg = sum(float(b.get("verified_quantity_kg") or b.get("quantity_kg") or 0.0) for b in completed_rows)
    total_inr = sum(float(b.get("final_amount") or 0.0) for b in completed_rows)

    # Next 7 days bookings count grid
    end_date = today_ist() + timedelta(days=settings.BOOKING_WINDOW_DAYS - 1)
    future_b_res = db.table("bookings")\
        .select("session_date, session_id")\
        .gte("session_date", curr_date_str)\
        .lte("session_date", end_date.isoformat())\
        .neq("status", "cancelled")\
        .execute()

    f_counts: Dict[tuple, int] = {}
    for r in (future_b_res.data or []):
        key = (r["session_date"], r["session_id"])
        f_counts[key] = f_counts.get(key, 0) + 1

    next_7_days = []
    for d_offset in range(settings.BOOKING_WINDOW_DAYS):
        d = today_ist() + timedelta(days=d_offset)
        d_str = d.isoformat()
        day_item = {
            "date": d_str,
            "day_name": d.strftime("%A"),
            "sessions": [
                {
                    "session_id": tmpl["id"],
                    "session_name": tmpl["name"],
                    "booked": f_counts.get((d_str, tmpl["id"]), 0),
                    "capacity": tmpl["capacity"]
                } for tmpl in tmpls
            ]
        }
        next_7_days.append(day_item)

    return AdminDashboardResponse(
        current_session=current_metric,
        today_sessions=today_metrics,
        next_7_days=next_7_days,
        totals_today=AdminDashboardTotals(
            customers_served_today=customers_served,
            total_kg_verified_today=round(total_kg, 2),
            total_inr_paid_today=round(total_inr, 2)
        )
    )


# ======================================================================
# BOOKINGS & CSV EXPORT
# ======================================================================

def _build_bookings_query(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session_id: Optional[int] = None,
    status: Optional[str] = None,
    crop_id: Optional[int] = None,
    q: Optional[str] = None
):
    db = get_db()
    query = db.table("bookings").select("*")

    if date_from:
        query = query.gte("session_date", date_from)
    if date_to:
        query = query.lte("session_date", date_to)
    if session_id:
        query = query.eq("session_id", session_id)
    if status:
        query = query.eq("status", status)
    if crop_id:
        query = query.eq("crop_id", crop_id)
    if q:
        query = query.or_(f"receipt_no.ilike.%{q}%,receipt_name.ilike.%{q}%")

    return query


@router.get("/bookings")
async def get_bookings_list(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session_id: Optional[int] = None,
    status: Optional[str] = None,
    crop_id: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_role("admin"))
):
    """Admin paginated booking history with multiple search filters."""
    query = _build_bookings_query(date_from, date_to, session_id, status, crop_id, q)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size - 1

    res = query.order("session_date", desc=True).order("created_at", desc=True).range(start_idx, end_idx).execute()
    items = res.data or []

    # Clean out sensitive QR tokens from admin output
    for item in items:
        item.pop("qr_token", None)

    return {
        "items": items,
        "page": page,
        "page_size": page_size
    }


@router.get("/bookings/{booking_id}")
async def get_booking_detail(booking_id: str, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Retrieve booking detail by ID for admin drawer."""
    db = get_db()
    res = db.table("bookings").select("*").eq("id", booking_id).limit(1).execute()
    if not res.data:
        raise NotFound("BOOKING_NOT_FOUND", "Booking not found.")

    booking = res.data[0]
    booking.pop("qr_token", None)

    # Customer profile
    cust_res = db.table("profiles").select("*").eq("id", booking["customer_id"]).limit(1).execute()
    customer = cust_res.data[0] if cust_res.data else {}

    return {
        "booking": booking,
        "customer": customer
    }


@router.get("/export/bookings.csv")
async def export_bookings_csv(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    session_id: Optional[int] = None,
    status: Optional[str] = None,
    crop_id: Optional[int] = None,
    q: Optional[str] = None,
    user: Dict[str, Any] = Depends(require_role("admin"))
):
    """Export filtered bookings to CSV."""
    query = _build_bookings_query(date_from, date_to, session_id, status, crop_id, q)
    res = query.order("session_date", desc=True).order("created_at", desc=True).limit(5000).execute()
    rows = res.data or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Receipt Number",
        "Session Date",
        "Session ID",
        "Customer Name",
        "Crop Name",
        "Declared Qty (kg)",
        "Verified Qty (kg)",
        "Price/kg (INR)",
        "Estimated Amount (INR)",
        "Final Amount (INR)",
        "Status",
        "Queue Number",
        "Payout Status",
        "Created At",
        "Completed At"
    ])

    for r in rows:
        writer.writerow([
            r.get("receipt_no"),
            r.get("session_date"),
            r.get("session_id"),
            r.get("receipt_name"),
            r.get("crop_name"),
            r.get("quantity_kg"),
            r.get("verified_quantity_kg") or "",
            r.get("price_per_kg"),
            r.get("estimated_amount"),
            r.get("final_amount") or "",
            r.get("status"),
            r.get("queue_number") or "",
            r.get("payout_status"),
            r.get("created_at"),
            r.get("completed_at") or ""
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=bookings_export_{today_ist().strftime('%Y%m%d')}.csv"}
    )


# ======================================================================
# CUSTOMERS DIRECTORY
# ======================================================================

@router.get("/customers")
async def get_customers(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_role("admin"))
):
    """Retrieve registered farmer customers."""
    db = get_db()
    query = db.table("profiles").select("*").eq("role", "customer")
    if q:
        query = query.or_(f"full_name.ilike.%{q}%,email.ilike.%{q}%,mobile.ilike.%{q}%")

    start_idx = (page - 1) * page_size
    res = query.order("created_at", desc=True).range(start_idx, start_idx + page_size - 1).execute()
    return {"items": res.data or [], "page": page, "page_size": page_size}


@router.get("/customers/{customer_id}")
async def get_customer_detail(customer_id: str, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Retrieve farmer profile along with booking history."""
    db = get_db()
    cust_res = db.table("profiles").select("*").eq("id", customer_id).limit(1).execute()
    if not cust_res.data:
        raise NotFound("CUSTOMER_NOT_FOUND", "Customer not found.")

    b_res = db.table("bookings")\
        .select("id, receipt_no, session_date, session_id, crop_name, quantity_kg, verified_quantity_kg, final_amount, status, created_at")\
        .eq("customer_id", customer_id)\
        .order("created_at", desc=True)\
        .execute()

    return {
        "profile": cust_res.data[0],
        "bookings": b_res.data or []
    }


# ======================================================================
# CROPS CATALOG
# ======================================================================

@router.get("/crops", response_model=List[AdminCropItem])
async def list_admin_crops(user: Dict[str, Any] = Depends(require_role("admin"))):
    """List all crops in system."""
    return get_all_crops_admin()


@router.post("/crops", response_model=AdminCropItem, status_code=status.HTTP_201_CREATED)
async def add_crop(payload: CreateCropRequest, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Create a new crop."""
    return create_crop(admin_id=user["id"], name=payload.name, emoji=payload.emoji, price_per_kg=payload.price_per_kg)


@router.put("/crops/{crop_id}", response_model=AdminCropItem)
async def modify_crop(crop_id: int, payload: UpdateCropRequest, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Update crop pricing or details."""
    return update_crop(
        admin_id=user["id"],
        crop_id=crop_id,
        name=payload.name,
        emoji=payload.emoji,
        price_per_kg=payload.price_per_kg,
        is_active=payload.is_active
    )


# ======================================================================
# STAFF ACCOUNTS
# ======================================================================

@router.get("/staff")
async def list_staff(user: Dict[str, Any] = Depends(require_role("admin"))):
    """List staff accounts (scanners and officers)."""
    db = get_db()
    res = db.table("profiles").select("id, role, full_name, email, is_active, created_at").in_("role", ["scanner", "officer"]).order("created_at", desc=True).execute()
    return res.data or []


@router.post("/staff", status_code=status.HTTP_201_CREATED)
async def create_staff(payload: CreateStaffRequest, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Create a new gate scanner or desk officer account."""
    db = get_db()

    # Check email exists
    exist = db.table("profiles").select("id").eq("email", payload.email.lower()).execute()
    if exist.data:
        raise BadRequest("EMAIL_EXISTS", "A user with this email already exists.")

    auth_id = None
    try:
        auth_res = db.auth.admin.create_user({
            "email": payload.email.lower(),
            "password": payload.password,
            "email_confirm": True,
            "user_metadata": {"full_name": payload.full_name, "role": payload.role}
        })
        if not auth_res.user:
            raise BadRequest("AUTH_ERROR", "Failed to create staff credentials.")
        auth_id = auth_res.user.id
    except Exception as e:
        raise BadRequest("AUTH_ERROR", str(e))

    try:
        db.table("profiles").insert({
            "id": auth_id,
            "role": payload.role,
            "full_name": payload.full_name.strip(),
            "email": payload.email.lower(),
            "is_active": True
        }).execute()
    except Exception as e:
        if auth_id:
            try:
                db.auth.admin.delete_user(auth_id)
            except Exception:
                pass
        raise BadRequest("PROFILE_ERROR", str(e))

    record_audit(
        actor_id=user["id"],
        action="CREATE_STAFF",
        entity="profiles",
        entity_id=auth_id,
        details={"role": payload.role, "email": payload.email.lower()}
    )

    return {"message": f"Staff account created for {payload.full_name}", "id": auth_id}


@router.patch("/staff/{staff_id}")
async def toggle_staff_status(staff_id: str, payload: UpdateStaffStatusRequest, user: Dict[str, Any] = Depends(require_role("admin"))):
    """Activate or deactivate staff member account."""
    db = get_db()
    res = db.table("profiles").update({"is_active": payload.is_active}).eq("id", staff_id).execute()
    if not res.data:
        raise NotFound("STAFF_NOT_FOUND", "Staff member not found.")

    record_audit(
        actor_id=user["id"],
        action="UPDATE_STAFF_STATUS",
        entity="profiles",
        entity_id=staff_id,
        details={"is_active": payload.is_active}
    )

    status_str = "activated" if payload.is_active else "deactivated"
    return {"message": f"Staff account {status_str} successfully"}


# ======================================================================
# AUDIT LOG
# ======================================================================

@router.get("/audit-log")
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: Dict[str, Any] = Depends(require_role("admin"))
):
    """Retrieve audit log events."""
    db = get_db()
    start_idx = (page - 1) * page_size
    res = db.table("audit_log").select("*").order("created_at", desc=True).range(start_idx, start_idx + page_size - 1).execute()
    return {"items": res.data or [], "page": page, "page_size": page_size}

