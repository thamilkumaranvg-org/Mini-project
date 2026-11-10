"""Standardized error responses and error mapping for Farmer Slot Booking System."""
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details or {}})
        self.code = code
        self.message = message
        self.details = details or {}


# Convenience factory helpers
def BadRequest(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, code, message, details)

def Unauthorized(code: str = "UNAUTHORIZED", message: str = "Authentication required.") -> AppError:
    return AppError(status.HTTP_401_UNAUTHORIZED, code, message)

def Forbidden(code: str = "FORBIDDEN", message: str = "Access forbidden.") -> AppError:
    return AppError(status.HTTP_403_FORBIDDEN, code, message)

def NotFound(code: str = "NOT_FOUND", message: str = "Resource not found.") -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, code, message)

def Conflict(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> AppError:
    return AppError(status.HTTP_409_CONFLICT, code, message, details)


RPC_ERROR_MAP = {
    "SESSION_FULL": (status.HTTP_409_CONFLICT, "SESSION_FULL", "This session is full. Please choose another slot."),
    "ALREADY_BOOKED": (status.HTTP_409_CONFLICT, "ALREADY_BOOKED", "You already have an active booking for this session."),
    "CROP_UNAVAILABLE": (status.HTTP_400_BAD_REQUEST, "CROP_UNAVAILABLE", "Selected crop is inactive or unavailable."),
    "INVALID_SESSION": (status.HTTP_400_BAD_REQUEST, "INVALID_SESSION", "Invalid session template selected."),
    "INVALID_QR": (status.HTTP_400_BAD_REQUEST, "INVALID_QR", "QR code is invalid or unrecognized."),
    "BOOKING_CANCELLED": (status.HTTP_400_BAD_REQUEST, "BOOKING_CANCELLED", "This booking was cancelled."),
    "ALREADY_CHECKED_IN": (status.HTTP_400_BAD_REQUEST, "ALREADY_CHECKED_IN", "Customer has already checked in."),
    "SESSION_ENDED": (status.HTTP_400_BAD_REQUEST, "SESSION_ENDED", "This session has already ended."),
    "WRONG_DAY": (status.HTTP_400_BAD_REQUEST, "WRONG_DAY", "QR code is valid for a different date."),
    "SESSION_NOT_STARTED": (status.HTTP_400_BAD_REQUEST, "SESSION_NOT_STARTED", "Check-in for this session has not started yet."),
    "ALREADY_SERVING": (status.HTTP_400_BAD_REQUEST, "ALREADY_SERVING", "You are already serving a customer. Complete or mark no-show first."),
    "QUEUE_EMPTY": (status.HTTP_404_NOT_FOUND, "QUEUE_EMPTY", "No waiting customers in the queue for this session."),
    "NOT_CALLED": (status.HTTP_400_BAD_REQUEST, "NOT_CALLED", "This customer is not currently called by you."),
    "INVALID_QUANTITY": (status.HTTP_400_BAD_REQUEST, "INVALID_QUANTITY", "Verified quantity must be greater than 0 kg."),
    "CANNOT_CANCEL": (status.HTTP_400_BAD_REQUEST, "CANNOT_CANCEL", "Booking can only be cancelled before session start."),
    "BOOKING_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "BOOKING_NOT_FOUND", "Booking not found."),
    "FORBIDDEN": (status.HTTP_403_FORBIDDEN, "FORBIDDEN", "You do not have permission for this action.")
}


def parse_db_exception(exc: Exception) -> AppError:
    """Parse Postgres/Supabase RPC exceptions and map to friendly AppError."""
    msg = str(exc)
    for code, (status_code, err_code, err_msg) in RPC_ERROR_MAP.items():
        if code in msg:
            return AppError(status_code, err_code, err_msg)
    return AppError(status.HTTP_500_INTERNAL_SERVER_ERROR, "DATABASE_ERROR", "A database error occurred.")


def error_json_response(code: str, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}}
    )

