"""Officer desk routes: calling queue, profile inspection while called, weight verification, cash payout settlement."""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, Body
from app.security import require_role
from app.services.queue import (
    get_officer_today_sessions,
    get_officer_tomorrow_sessions,
    get_officer_waiting_queue,
    officer_call_next,
    get_officer_current_called,
    officer_complete_booking,
    officer_mark_no_show,
    get_officer_completed_today
)
from app.schemas import (
    OfficerSessionSummary,
    OfficerTomorrowSessionSummary,
    OfficerQueueItem,
    OfficerCalledBookingResponse,
    CompleteBookingRequest,
    OfficerCompletedRecord
)

router = APIRouter(prefix="/api/officer", tags=["officer"])


@router.get("/sessions/today", response_model=List[OfficerSessionSummary])
async def get_today_sessions(user: Dict[str, Any] = Depends(require_role("officer"))):
    """Retrieve all sessions for today with live queue counts and status."""
    return get_officer_today_sessions()


@router.get("/sessions/tomorrow", response_model=List[OfficerTomorrowSessionSummary])
async def get_tomorrow_sessions(user: Dict[str, Any] = Depends(require_role("officer"))):
    """Retrieve session booked counts and remaining capacity for tomorrow."""
    return get_officer_tomorrow_sessions()


@router.get("/queue", response_model=List[OfficerQueueItem])
async def get_waiting_queue(
    session_id: int = Query(..., ge=1, le=3),
    user: Dict[str, Any] = Depends(require_role("officer"))
):
    """R9: Officer sees only queue_number + receipt_name + checked_in_at for waiting customers."""
    return get_officer_waiting_queue(session_id=session_id)


@router.post("/call-next", response_model=OfficerCalledBookingResponse)
async def call_next_customer(
    payload: Dict[str, int] = Body(...),
    user: Dict[str, Any] = Depends(require_role("officer"))
):
    """Atomically call the next checked-in customer in FIFO order."""
    session_id = payload.get("session_id", 1)
    return officer_call_next(officer_profile=user, session_id=session_id)


@router.get("/current", response_model=Optional[OfficerCalledBookingResponse])
async def get_current_called(user: Dict[str, Any] = Depends(require_role("officer"))):
    """Return currently called customer for this officer (profile is accessible ONLY while called)."""
    return get_officer_current_called(officer_profile=user)


@router.post("/bookings/{booking_id}/complete", response_model=OfficerCompletedRecord)
async def complete_booking(
    booking_id: str,
    payload: CompleteBookingRequest,
    user: Dict[str, Any] = Depends(require_role("officer"))
):
    """Verify weight, compute final amount with price snapshot, confirm cash paid and mark completed."""
    return officer_complete_booking(
        officer_profile=user,
        booking_id=booking_id,
        verified_qty=payload.verified_quantity_kg
    )


@router.post("/bookings/{booking_id}/no-show")
async def mark_no_show(
    booking_id: str,
    user: Dict[str, Any] = Depends(require_role("officer"))
):
    """Mark a called customer as No-Show."""
    officer_mark_no_show(officer_profile=user, booking_id=booking_id)
    return {"message": "Customer marked as No-Show"}


@router.get("/completed-today", response_model=List[OfficerCompletedRecord])
async def get_completed_today(user: Dict[str, Any] = Depends(require_role("officer"))):
    """R9: Receipt-level data of today's completed transactions (no farmer profile data)."""
    return get_officer_completed_today(officer_profile=user)

