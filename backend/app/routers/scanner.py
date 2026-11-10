"""Gate Scanner routes: scan token check-in, live session and queue tracking."""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query
from app.security import require_role
from app.services.queue import (
    process_scanner_checkin,
    get_scanner_current_session,
    get_scanner_queue
)
from app.schemas import (
    ScanRequest,
    ScanSuccessResponse,
    ScannerQueueItemResponse,
    ScannerCurrentSessionResponse
)

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@router.post("/scan", response_model=ScanSuccessResponse)
async def scan_qr_token(payload: ScanRequest, user: Dict[str, Any] = Depends(require_role("scanner"))):
    """Process gate QR scan and place customer into FIFO queue."""
    return process_scanner_checkin(scanner_profile=user, qr_token=payload.token)


@router.get("/current-session", response_model=ScannerCurrentSessionResponse)
async def get_current_session(user: Dict[str, Any] = Depends(require_role("scanner"))):
    """Retrieve current or next session status for scanner gate."""
    return get_scanner_current_session()


@router.get("/queue", response_model=List[ScannerQueueItemResponse])
async def get_session_queue(
    session_id: int = Query(..., ge=1, le=3),
    user: Dict[str, Any] = Depends(require_role("scanner"))
):
    """Retrieve checked-in queue for today's session (R8: receipt name, queue #, check-in time ONLY)."""
    return get_scanner_queue(session_id=session_id)

