# Farmer Slot Booking System (Session-wise Produce Selling Slots)

A production-grade, full-stack government procurement slot booking application built with **FastAPI**, **Vanilla HTML5/CSS3/JavaScript (ES modules)**, and **Supabase Postgres**.

---

## 🌾 Overview & Business Purpose

Farmers often waste hours in disorganized queues at government procurement centers. This system enforces structured, session-wise produce selling slots so farmers arrive at their designated window, scan a secure entry QR code at the gate, receive a sequential FIFO queue position (1..8), and have their produce verified and settled in cash without waiting.

### Daily Session Windows (Asia/Kolkata Timezone)
- **Session 1**: 09:00 - 11:00 (Capacity: 8 farmers)
- **Session 2**: 11:20 - 13:20 (Capacity: 8 farmers)
- **Session 3**: 14:00 - 16:00 (Capacity: 8 farmers)
- **Total Center Capacity**: 24 farmers per day

---

## 🏛️ Four Distinct Portals & URLs

| Portal | URL | Purpose & Capabilities |
| :--- | :--- | :--- |
| **Farmer (Customer)** | [`http://localhost:8000/login.html`](http://localhost:8000/login.html) | Register profile, browse 7-day slot availability, reserve crop selling slot, generate printable receipt with entry QR pass, track FIFO queue position and cash payout status. |
| **Farmer Registration** | [`http://localhost:8000/register.html`](http://localhost:8000/register.html) | Farmer onboarding with age validation (>= 18), mobile regex, and dynamic Indian states/districts cascade. |
| **Gate Scanner** | [`http://localhost:8000/scanner/login.html`](http://localhost:8000/scanner/login.html) | Gate staff camera check-in (HTML5-QRCode) with fallback token input, atomic FIFO queue assignment (1..8), large visual green tick/red cross modal. Zero profile or QR leaks. |
| **Desk Officer** | [`http://localhost:8000/officer/login.html`](http://localhost:8000/officer/login.html) | Counter officer calling queue (`FOR UPDATE SKIP LOCKED`), privacy-gated farmer profile access (visible strictly while called), verified weight entry, live payout math, cash settlement. |
| **Administrator** | [`http://localhost:8000/admin/login.html`](http://localhost:8000/admin/login.html) | Live session monitoring, 7-day future booking matrix, historical bookings with CSV export, farmer directory, MSP crop catalog with historical price audit, staff provisioning. |

---

## 🗄️ Supabase Database Setup (Mandatory)

Execute the SQL scripts in the **Supabase Dashboard -> SQL Editor** in the following order:

1. **`database/schema.sql`**:
   - Creates extensions (`uuid-ossp`, `pgcrypto`).
   - Creates tables: `profiles`, `session_templates`, `crops`, `crop_price_history`, `bookings`, `notifications`, `audit_log`.
   - Enables Row Level Security (RLS) on all tables with **zero public policies** (backend accesses data securely via the `SERVICE_ROLE` key).
2. **`database/functions.sql`**:
   - Creates atomic database procedures:
     - `fn_book_slot`: Enforces 8-capacity limit per session under advisory transaction locks; snapshots crop price.
     - `fn_check_in`: QR token validation, timing window enforcement, and atomic FIFO queue number assignment (`1..8`).
     - `fn_call_next`: `FOR UPDATE SKIP LOCKED` caller ensuring single active serving per officer.
     - `fn_complete_booking`: Computes final cash amount from verified scale weight and price snapshot.
     - `fn_mark_no_show`: No-show handler.
     - `fn_cancel_booking`: Customer cancellation with immediate seat release.
     - `fn_expire_bookings`: Automatic background expiry daemon for missed slots.
     - `fn_availability`: Aggregates active seat counts.
3. **`database/seed.sql`**:
   - Seeds the 3 fixed daily sessions with capacity 8.
   - Seeds ~12 standard crops with initial reference MSP prices (Paddy, Wheat, Maize, Ragi, Bajra, Jowar, Groundnut, Cotton, Turmeric, Black gram, Green gram, Sugarcane).

---

## ⚙️ Environment Configuration

Copy `backend/.env.example` to `backend/.env` and update credentials:

```bash
cp backend/.env.example backend/.env
```

Key environment variables:
```ini
APP_ENV=development
APP_BASE_URL=http://localhost:8000

# Supabase Credentials (from Project Settings -> API)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOi...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...

COOKIE_SECURE=false
TIMEZONE=Asia/Kolkata
BOOKING_WINDOW_DAYS=7
ALMOST_FULL_THRESHOLD=2
MAX_QUANTITY_KG=10000

# Development clock override (optional ISO 8601 string)
# TIME_OVERRIDE_ISO=2026-11-09T09:30:00+05:30

# Email: console (logs to terminal) | resend | smtp
EMAIL_PROVIDER=console
EMAIL_FROM=no-reply@farmerslotbooking.gov.in

# Bootstrap Administrator
ADMIN_EMAIL=admin@slotbooking.gov.in
ADMIN_PASSWORD=AdminSecurePassword123!
ADMIN_FULL_NAME="Super Administrator"
```

---

## 🚀 Installation & Running the Server

### 1. Install Dependencies
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\pip install -r backend/requirements.txt
# Linux / macOS:
# source .venv/bin/activate && pip install -r backend/requirements.txt
```

### 2. Bootstrap Initial Administrator Account
```bash
python scripts/create_admin.py
```

### 3. (Optional) Seed Demo Staff & Customer for Local Testing
```bash
python scripts/seed_demo.py
```
*Creates:*
- **Scanner**: `scanner@slotbooking.gov.in` / `ScannerPass123!`
- **Officer**: `officer@slotbooking.gov.in` / `OfficerPass123!`
- **Farmer**: `farmer@example.com` / `FarmerPass123!`

### 4. Start the Application Server
```bash
.\.venv\Scripts\uvicorn app.main:app --app-dir backend --port 8000 --reload
```
Open your browser at `http://localhost:8000`.

---

## 🧪 Automated Testing

Run the complete automated pytest suite:
```bash
.\.venv\Scripts\pytest -c backend/pytest.ini backend/tests -v
```

All 18 automated tests cover:
- Capacity enforcement (9th booking rejection; concurrent race condition prevention).
- Availability labels (`Available`, `Almost full` <=2 left, `Full`).
- Exclusion of today's ended sessions.
- Duplicate active booking prevention and cancellation seat release.
- QR token single-use opacity (no personal data leakage) and validation window.
- Sequential FIFO queue assignment (`1..8`).
- Officer privacy enforcement (waiting queue contains zero profile fields; profile visible strictly while called; 403 post-completion).
- Price snapshot immutability (later admin price revisions never alter existing bookings).
- Expiry daemon transitions (unscanned slots become `missed`, checked-in slots remain servable).
- RBAC guards and CSRF header verification (`X-Requested-With: fetch`).

---

## 📋 Business Rules Implementation Matrix

| Rule | Specification | Implemented In |
| :--- | :--- | :--- |
| **R1** | Fixed 3 daily sessions in Asia/Kolkata; clock override support via `TIME_OVERRIDE_ISO`. | `clock.py`, `sessions.py`, `schema.sql` |
| **R2** | 7-day booking window; today's ended sessions excluded from availability. | `sessions.py`, `slots.html` |
| **R3** | Remaining seats labels: 0 -> "Full", 1..2 -> "Almost full", >=3 -> "Available (N seats left)". | `sessions.py`, `test_availability_and_capacity.py` |
| **R4** | One active booking per farmer per date+session; atomic capacity 8 check in database. | `fn_book_slot`, `bookings.py` |
| **R5** | Price snapshotting into booking; server computes estimated amount; final amount based on snapshot. | `fn_book_slot`, `fn_complete_booking`, `pricing.py` |
| **R6** | Receipt displays `receipt_no`, `receipt_name` (full_name ONLY), timings, crop, declared qty, QR code. | `format_booking_receipt`, `receipt.html` |
| **R7** | QR encodes opaque random token (`secrets.token_urlsafe(32)`); never personal data; owner only. | `qr.py`, `test_qr_and_checkin.py` |
| **R8** | Check-in assigns atomic sequential FIFO queue number (`1..8`); visual green tick / red cross. | `fn_check_in`, `queue.py`, `scan.html` |
| **R9** | Server-side officer privacy: zero profile data in queue; profile visible strictly while called; 403 after. | `schemas.py`, `queue.py`, `desk.html` |
| **R10** | "Call Next" uses `FOR UPDATE SKIP LOCKED`; 1 active called customer per officer at a time. | `fn_call_next`, `queue.py` |
| **R11** | Verified quantity entry, final cash amount calculation, completion and no-show handling. | `fn_complete_booking`, `fn_mark_no_show` |
| **R12** | Session end: checked-in customers still served (queue drains); unscanned become `missed`. | `fn_expire_bookings`, `jobs.py` |
| **R13** | Cancellation allowed before session start for status `booked`; immediately releases seat. | `fn_cancel_booking`, `bookings.py` |
| **R14** | Registration validations: unique email/mobile (`^[6-9][0-9]{9}$`), age >= 18, Indian districts JSON. | `schemas.py`, `register.html` |
| **R15** | Admin manages crops and staff; crop price history tracking; tamper-evident audit logging. | `pricing.py`, `admin.py`, `crops.html`, `staff.html` |

