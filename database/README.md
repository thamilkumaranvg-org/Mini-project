# Supabase Database Setup Guide

This guide provides step-by-step instructions to initialize the Supabase Postgres database for the Farmer Slot Booking System.

---

## Prerequisites
1. A Supabase Project created at [https://supabase.com](https://supabase.com).
2. Access to your project's **SQL Editor** in the Supabase Dashboard.
3. Your Project API credentials from **Project Settings -> API**:
   - `Project URL`
   - `anon public` key
   - `service_role` secret key (keep this strictly confidential; used only in `backend/.env`)

---

## Execution Order

In the Supabase Dashboard, navigate to **SQL Editor -> New query** and execute the scripts in the following order:

### Step 1: Run `schema.sql`
- **File**: `database/schema.sql`
- **Purpose**: Creates extensions (`uuid-ossp`, `pgcrypto`), tables (`profiles`, `session_templates`, `crops`, `crop_price_history`, `bookings`, `notifications`, `audit_log`), updated-at triggers, constraints, indexes, and enables Row Level Security (RLS) on all tables with no public policies.
- **Verification**: Check **Database -> Tables** to confirm 7 tables exist with RLS enabled.

### Step 2: Run `functions.sql`
- **File**: `database/functions.sql`
- **Purpose**: Creates the atomic transactional procedures:
  - `fn_book_slot`: Concurrency-safe slot reservation with capacity enforcement (max 8) and price snapshotting.
  - `fn_check_in`: QR token validation and atomic FIFO queue number assignment (`1..8`).
  - `fn_call_next`: `FOR UPDATE SKIP LOCKED` caller ensuring single-active serving per officer.
  - `fn_complete_booking`: Weight verification and cash payout settlement calculation.
  - `fn_mark_no_show`: No-show status handler.
  - `fn_cancel_booking`: Pre-session cancellation with seat release.
  - `fn_expire_bookings`: Expiry daemon logic for missed slots and past-day items.
  - `fn_availability`: Fast slot seat counter.
- **Verification**: Run `SELECT * FROM public.session_templates;` or test a dummy call.

### Step 3: Run `seed.sql`
- **File**: `database/seed.sql`
- **Purpose**: Inserts the 3 fixed daily sessions (09:00-11:00, 11:20-13:20, 14:00-16:00) with capacity 8, and seeds 12 standard crops with initial price snapshots.
- **Verification**:
  ```sql
  SELECT count(*) FROM public.session_templates; -- Expected: 3
  SELECT count(*) FROM public.crops;             -- Expected: 12
  ```

---

## Security & Row Level Security (RLS)
- All tables have RLS enabled with **zero public policies**.
- The frontend has NO direct Supabase database access.
- The FastAPI backend interacts with Supabase using the **`service_role` key**, bypassing RLS securely on the server side after verifying user sessions and enforcing role-based access control.

