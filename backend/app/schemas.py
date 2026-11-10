"""Pydantic schemas with strict role/state separation and server-side privacy enforcement."""
from datetime import date, time, datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# ======================================================================
# AUTH & PROFILE SCHEMAS
# ======================================================================

class RegisterCustomerRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=100)
    mobile: str = Field(pattern=r"^[6-9][0-9]{9}$")
    dob: date
    gender: str = Field(pattern=r"^(male|female)$")
    state: str = Field(min_length=2, max_length=60)
    district: str = Field(min_length=2, max_length=60)
    address: str = Field(min_length=5, max_length=300)

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, v: date) -> date:
        today = date.today()
        if v > today:
            raise ValueError("Date of birth cannot be in the future")
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18:
            raise ValueError("Farmer must be at least 18 years old")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    portal: str = Field(pattern=r"^(customer|scanner|officer|admin)$")


class UserProfileResponse(BaseModel):
    id: str
    role: str
    full_name: str
    email: str
    mobile: Optional[str] = None
    dob: Optional[date] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    is_active: bool
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    mobile: Optional[str] = Field(None, pattern=r"^[6-9][0-9]{9}$")
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, pattern=r"^(male|female)$")
    state: Optional[str] = Field(None, min_length=2, max_length=60)
    district: Optional[str] = Field(None, min_length=2, max_length=60)
    address: Optional[str] = Field(None, min_length=5, max_length=300)

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, v: Optional[date]) -> Optional[date]:
        if v is not None:
            today = date.today()
            if v > today:
                raise ValueError("Date of birth cannot be in the future")
            age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
            if age < 18:
                raise ValueError("Farmer must be at least 18 years old")
        return v


# ======================================================================
# CROPS & SESSIONS SCHEMAS
# ======================================================================

class CropResponse(BaseModel):
    id: int
    name: str
    emoji: Optional[str] = None
    price_per_kg: float
    is_active: bool


class SessionTemplateResponse(BaseModel):
    id: int
    name: str
    start_time: str
    end_time: str
    capacity: int


class SessionAvailability(BaseModel):
    session_id: int
    name: str
    start_time: str
    end_time: str
    capacity: int
    booked_count: int
    remaining_seats: int
    status_label: str  # Available, Almost full, Full
    is_bookable: bool


class DayAvailabilityResponse(BaseModel):
    date: date
    is_today: bool
    sessions: List[SessionAvailability]


# ======================================================================
# BOOKING & RECEIPT SCHEMAS (CUSTOMER VIEW)
# ======================================================================

class CreateBookingRequest(BaseModel):
    session_date: date
    session_id: int
    crop_id: int
    quantity_kg: float = Field(gt=0, le=10000.0)

    @field_validator("quantity_kg")
    @classmethod
    def validate_two_decimals(cls, v: float) -> float:
        return round(v, 2)


class BookingReceiptResponse(BaseModel):
    id: str
    receipt_no: str
    receipt_name: str  # Farmer full_name snapshot ONLY
    session_date: date
    session_id: int
    session_name: str
    start_time: str
    end_time: str
    crop_id: int
    crop_name: str
    declared_quantity_kg: float
    price_per_kg: float
    estimated_amount: float
    status: str
    queue_number: Optional[int] = None
    checked_in_at: Optional[datetime] = None
    called_at: Optional[datetime] = None
    verified_quantity_kg: Optional[float] = None
    final_amount: Optional[float] = None
    payout_status: str
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    # QR is returned as base64 data URI ONLY when status='booked' and session not ended
    qr_png_data_uri: Optional[str] = None
    validity_text: str
    is_expired: bool
    can_cancel: bool


class BookingSummaryResponse(BaseModel):
    id: str
    receipt_no: str
    session_date: date
    session_id: int
    session_name: str
    start_time: str
    end_time: str
    crop_name: str
    declared_quantity_kg: float
    estimated_amount: float
    status: str
    queue_number: Optional[int] = None
    final_amount: Optional[float] = None
    payout_status: str
    created_at: datetime


# ======================================================================
# SCANNER SCHEMAS
# ======================================================================

class ScanRequest(BaseModel):
    token: str = Field(min_length=10)


class ScanSuccessResponse(BaseModel):
    success: bool = True
    receipt_no: str
    receipt_name: str
    session_name: str
    queue_number: int
    checked_in_at: datetime


class ScannerQueueItemResponse(BaseModel):
    queue_number: int
    receipt_name: str
    checked_in_at: datetime


class ScannerCurrentSessionResponse(BaseModel):
    session_id: int
    session_name: str
    start_time: str
    end_time: str
    is_active_now: bool
    total_booked: int
    checked_in_count: int
    waiting_count: int


# ======================================================================
# OFFICER SCHEMAS (STRICT PRIVACY CONTROL - R9)
# ======================================================================

class OfficerSessionSummary(BaseModel):
    session_id: int
    session_name: str
    start_time: str
    end_time: str
    capacity: int
    booked_count: int
    checked_in_count: int
    waiting_count: int
    serving_count: int
    completed_count: int
    no_show_count: int
    remaining_seats: int
    session_status: str  # upcoming, in_progress, ended


class OfficerTomorrowSessionSummary(BaseModel):
    session_id: int
    session_name: str
    session_date: str
    start_time: str
    end_time: str
    capacity: int
    booked_count: int
    remaining_seats: int
    status_label: str  # Available, Almost full, Full


class OfficerQueueItem(BaseModel):
    queue_number: int
    receipt_name: str
    checked_in_at: datetime


class OfficerCalledProfile(BaseModel):
    full_name: str
    dob: Optional[date] = None
    gender: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    mobile: Optional[str] = None


class OfficerCalledBookingResponse(BaseModel):
    booking_id: str
    receipt_no: str
    queue_number: int
    session_name: str
    crop_name: str
    declared_quantity_kg: float
    price_per_kg: float
    estimated_amount: float
    called_at: datetime
    # Farmer profile is accessible ONLY while called
    profile: OfficerCalledProfile


class CompleteBookingRequest(BaseModel):
    verified_quantity_kg: float = Field(gt=0, le=10000.0)

    @field_validator("verified_quantity_kg")
    @classmethod
    def validate_two_decimals(cls, v: float) -> float:
        return round(v, 2)


class OfficerCompletedRecord(BaseModel):
    booking_id: str
    receipt_no: str
    receipt_name: str
    crop_name: str
    declared_quantity_kg: float
    verified_quantity_kg: float
    price_per_kg: float
    final_amount: float
    completed_at: datetime


# ======================================================================
# ADMIN SCHEMAS
# ======================================================================

class AdminSessionMetric(BaseModel):
    session_id: int
    name: str
    timing: str
    status: str
    capacity: int
    booked: int
    checked_in: int
    waiting: int
    serving: int
    completed: int
    no_shows: int
    seats_remaining: int


class AdminDashboardTotals(BaseModel):
    customers_served_today: int
    total_kg_verified_today: float
    total_inr_paid_today: float


class AdminDashboardResponse(BaseModel):
    current_session: Optional[AdminSessionMetric] = None
    today_sessions: List[AdminSessionMetric]
    next_7_days: List[dict]
    totals_today: AdminDashboardTotals


class AdminCropItem(BaseModel):
    id: int
    name: str
    emoji: Optional[str] = None
    price_per_kg: float
    is_active: bool
    updated_at: datetime


class CreateCropRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    emoji: Optional[str] = None
    price_per_kg: float = Field(gt=0)


class UpdateCropRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    emoji: Optional[str] = None
    price_per_kg: Optional[float] = Field(None, gt=0)
    is_active: Optional[bool] = None


class CreateStaffRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=100)
    role: str = Field(pattern=r"^(scanner|officer)$")


class UpdateStaffStatusRequest(BaseModel):
    is_active: bool


class AuditLogItem(BaseModel):
    id: int
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    action: str
    entity: str
    entity_id: Optional[str] = None
    details: Optional[Any] = None
    created_at: datetime


# ======================================================================
# NOTIFICATIONS SCHEMAS
# ======================================================================

class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
    booking_id: Optional[str] = None

