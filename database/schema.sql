-- ======================================================================
-- Farmer Slot Booking System: Database Schema (Supabase Postgres)
-- Idempotent setup for all required tables, constraints, indexes, and RLS
-- ======================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. UPDATED_AT TRIGGER FUNCTION
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. PROFILES TABLE
-- References auth.users(id) on delete cascade
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'scanner', 'officer', 'admin')),
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    mobile TEXT UNIQUE,
    dob DATE,
    gender TEXT CHECK (gender IN ('male', 'female')),
    state TEXT,
    district TEXT,
    address TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_customer_profile CHECK (
        role <> 'customer' OR (
            dob IS NOT NULL AND
            gender IS NOT NULL AND
            state IS NOT NULL AND
            district IS NOT NULL AND
            address IS NOT NULL AND
            mobile IS NOT NULL
        )
    )
);

-- 4. SESSION_TEMPLATES TABLE
CREATE TABLE IF NOT EXISTS public.session_templates (
    id SMALLINT PRIMARY KEY,
    name TEXT NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    capacity INT NOT NULL DEFAULT 8
);

-- 5. CROPS TABLE
CREATE TABLE IF NOT EXISTS public.crops (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    emoji TEXT,
    price_per_kg NUMERIC(10,2) NOT NULL CHECK (price_per_kg > 0),
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID REFERENCES public.profiles(id)
);

-- Trigger for crops updated_at
DROP TRIGGER IF EXISTS trg_crops_updated_at ON public.crops;
CREATE TRIGGER trg_crops_updated_at
BEFORE UPDATE ON public.crops
FOR EACH ROW
EXECUTE FUNCTION update_timestamp_column();

-- 6. CROP_PRICE_HISTORY TABLE
CREATE TABLE IF NOT EXISTS public.crop_price_history (
    id BIGSERIAL PRIMARY KEY,
    crop_id INT NOT NULL REFERENCES public.crops(id) ON DELETE CASCADE,
    old_price NUMERIC(10,2),
    new_price NUMERIC(10,2) NOT NULL,
    changed_by UUID REFERENCES public.profiles(id),
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. BOOKINGS TABLE
CREATE TABLE IF NOT EXISTS public.bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_no TEXT UNIQUE NOT NULL,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    receipt_name TEXT NOT NULL,
    session_date DATE NOT NULL,
    session_id SMALLINT NOT NULL REFERENCES public.session_templates(id),
    crop_id INT REFERENCES public.crops(id),
    crop_name TEXT NOT NULL,
    quantity_kg NUMERIC(10,2) NOT NULL CHECK (quantity_kg > 0),
    price_per_kg NUMERIC(10,2) NOT NULL,
    estimated_amount NUMERIC(12,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked', 'checked_in', 'called', 'completed', 'missed', 'no_show', 'cancelled')),
    qr_token TEXT UNIQUE NOT NULL,
    queue_number SMALLINT CHECK (queue_number > 0),
    checked_in_at TIMESTAMPTZ,
    checked_in_by UUID REFERENCES public.profiles(id),
    called_at TIMESTAMPTZ,
    called_by UUID REFERENCES public.profiles(id),
    verified_quantity_kg NUMERIC(10,2),
    final_amount NUMERIC(12,2),
    payout_status TEXT NOT NULL DEFAULT 'pending' CHECK (payout_status IN ('pending', 'paid', 'not_applicable')),
    paid_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_session_queue UNIQUE (session_date, session_id, queue_number)
);

-- Unique index ensuring at most one active booking per customer per date+session
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_booking_per_session
ON public.bookings (customer_id, session_date, session_id)
WHERE status IN ('booked', 'checked_in', 'called', 'completed');

-- Additional performance indexes on bookings
CREATE INDEX IF NOT EXISTS idx_bookings_date_session_status
ON public.bookings (session_date, session_id, status);

CREATE INDEX IF NOT EXISTS idx_bookings_customer_history
ON public.bookings (customer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bookings_qr_token
ON public.bookings (qr_token);

-- Trigger for bookings updated_at
DROP TRIGGER IF EXISTS trg_bookings_updated_at ON public.bookings;
CREATE TRIGGER trg_bookings_updated_at
BEFORE UPDATE ON public.bookings
FOR EACH ROW
EXECUTE FUNCTION update_timestamp_column();

-- 8. NOTIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    booking_id UUID REFERENCES public.bookings(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK (type IN ('booking_confirmed', 'checked_in', 'called', 'completed', 'missed', 'cancelled')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    email_status TEXT DEFAULT 'pending' CHECK (email_status IN ('pending', 'sent', 'failed', 'skipped')),
    email_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
ON public.notifications (user_id, is_read, created_at DESC);

-- 9. AUDIT_LOG TABLE
CREATE TABLE IF NOT EXISTS public.audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
ON public.audit_log (created_at DESC);

-- 10. ROW LEVEL SECURITY (RLS)
-- Per specification: Enable RLS on every table with NO public policies so anon key cannot access data directly.
-- Backend communicates solely using the SERVICE ROLE key which bypasses RLS securely.
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crops ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crop_price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

