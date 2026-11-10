-- ======================================================================
-- Farmer Slot Booking System: Stored Functions & Procedures
-- ======================================================================

-- 1. fn_book_slot
-- Atomically books a seat if capacity allows, capturing price snapshot
CREATE OR REPLACE FUNCTION public.fn_book_slot(
    p_customer_id UUID,
    p_session_date DATE,
    p_session_id SMALLINT,
    p_crop_id INT,
    p_quantity_kg NUMERIC,
    p_receipt_name TEXT,
    p_receipt_no TEXT,
    p_qr_token TEXT
)
RETURNS public.bookings AS $$
DECLARE
    v_capacity INT;
    v_booked_count INT;
    v_crop_name TEXT;
    v_price_per_kg NUMERIC(10,2);
    v_estimated_amount NUMERIC(12,2);
    v_booking public.bookings;
BEGIN
    -- 1. Acquire transaction advisory lock for this exact (session_date, session_id)
    PERFORM pg_advisory_xact_lock(hashtextextended(p_session_date::text || '-' || p_session_id::text, 0));

    -- 2. Verify session template exists and retrieve capacity
    SELECT capacity INTO v_capacity
    FROM public.session_templates
    WHERE id = p_session_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'INVALID_SESSION';
    END IF;

    -- 3. Check for existing active booking for this customer on this date+session
    IF EXISTS (
        SELECT 1 FROM public.bookings
        WHERE customer_id = p_customer_id
          AND session_date = p_session_date
          AND session_id = p_session_id
          AND status IN ('booked', 'checked_in', 'called', 'completed')
    ) THEN
        RAISE EXCEPTION 'ALREADY_BOOKED';
    END IF;

    -- 4. Count current active bookings
    SELECT COUNT(*) INTO v_booked_count
    FROM public.bookings
    WHERE session_date = p_session_date
      AND session_id = p_session_id
      AND status <> 'cancelled';

    IF v_booked_count >= v_capacity THEN
        RAISE EXCEPTION 'SESSION_FULL';
    END IF;

    -- 5. Validate crop and fetch current price
    SELECT name, price_per_kg INTO v_crop_name, v_price_per_kg
    FROM public.crops
    WHERE id = p_crop_id AND is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'CROP_UNAVAILABLE';
    END IF;

    -- 6. Compute server-side estimated amount
    v_estimated_amount := ROUND((p_quantity_kg * v_price_per_kg), 2);

    -- 7. Insert booking row
    INSERT INTO public.bookings (
        receipt_no,
        customer_id,
        receipt_name,
        session_date,
        session_id,
        crop_id,
        crop_name,
        quantity_kg,
        price_per_kg,
        estimated_amount,
        status,
        qr_token,
        payout_status,
        created_at,
        updated_at
    ) VALUES (
        p_receipt_no,
        p_customer_id,
        p_receipt_name,
        p_session_date,
        p_session_id,
        p_crop_id,
        v_crop_name,
        p_quantity_kg,
        v_price_per_kg,
        v_estimated_amount,
        'booked',
        p_qr_token,
        'pending',
        NOW(),
        NOW()
    )
    RETURNING * INTO v_booking;

    RETURN v_booking;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 2. fn_check_in
-- Validates QR token and assigns strictly sequential FIFO queue number under lock
CREATE OR REPLACE FUNCTION public.fn_check_in(
    p_qr_token TEXT,
    p_scanner_id UUID,
    p_now TIMESTAMPTZ,
    p_open_minutes INT DEFAULT 0
)
RETURNS public.bookings AS $$
DECLARE
    v_booking public.bookings;
    v_start_time TIME;
    v_end_time TIME;
    v_start_ts TIMESTAMPTZ;
    v_end_ts TIMESTAMPTZ;
    v_open_ts TIMESTAMPTZ;
    v_today_ist DATE;
    v_next_queue SMALLINT;
BEGIN
    -- 1. Validate token existence
    SELECT * INTO v_booking
    FROM public.bookings
    WHERE qr_token = p_qr_token;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'INVALID_QR';
    END IF;

    -- 2. Validate booking status
    IF v_booking.status = 'cancelled' THEN
        RAISE EXCEPTION 'BOOKING_CANCELLED';
    END IF;

    IF v_booking.status IN ('checked_in', 'called', 'completed', 'no_show') THEN
        RAISE EXCEPTION 'ALREADY_CHECKED_IN';
    END IF;

    IF v_booking.status = 'missed' THEN
        RAISE EXCEPTION 'SESSION_ENDED';
    END IF;

    -- 3. Validate day (Asia/Kolkata date)
    v_today_ist := (p_now AT TIME ZONE 'Asia/Kolkata')::DATE;
    IF v_booking.session_date <> v_today_ist THEN
        RAISE EXCEPTION 'WRONG_DAY';
    END IF;

    -- 4. Validate time window for the session
    SELECT start_time, end_time INTO v_start_time, v_end_time
    FROM public.session_templates
    WHERE id = v_booking.session_id;

    v_start_ts := ((v_booking.session_date::text || ' ' || v_start_time::text)::timestamp) AT TIME ZONE 'Asia/Kolkata';
    v_end_ts := ((v_booking.session_date::text || ' ' || v_end_time::text)::timestamp) AT TIME ZONE 'Asia/Kolkata';
    v_open_ts := v_start_ts - (COALESCE(p_open_minutes, 0) || ' minutes')::interval;

    IF p_now < v_open_ts THEN
        RAISE EXCEPTION 'SESSION_NOT_STARTED';
    END IF;

    IF p_now > v_end_ts THEN
        RAISE EXCEPTION 'SESSION_ENDED';
    END IF;

    -- 5. Lock session for atomic queue number assignment
    PERFORM pg_advisory_xact_lock(hashtextextended(v_booking.session_date::text || '-' || v_booking.session_id::text, 0));

    SELECT COALESCE(MAX(queue_number), 0) + 1 INTO v_next_queue
    FROM public.bookings
    WHERE session_date = v_booking.session_date
      AND session_id = v_booking.session_id;

    -- 6. Update booking
    UPDATE public.bookings
    SET status = 'checked_in',
        queue_number = v_next_queue,
        checked_in_at = p_now,
        checked_in_by = p_scanner_id,
        updated_at = p_now
    WHERE id = v_booking.id
    RETURNING * INTO v_booking;

    RETURN v_booking;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 3. fn_call_next
-- Calls the next checked-in farmer in FIFO order using FOR UPDATE SKIP LOCKED
CREATE OR REPLACE FUNCTION public.fn_call_next(
    p_officer_id UUID,
    p_session_date DATE,
    p_session_id SMALLINT,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS public.bookings AS $$
DECLARE
    v_booking_id UUID;
    v_booking public.bookings;
BEGIN
    -- 1. Ensure officer is not already serving a called customer
    IF EXISTS (
        SELECT 1 FROM public.bookings
        WHERE called_by = p_officer_id
          AND status = 'called'
    ) THEN
        RAISE EXCEPTION 'ALREADY_SERVING';
    END IF;

    -- 2. Pick next waiting customer strictly by lowest queue_number with row lock
    SELECT id INTO v_booking_id
    FROM public.bookings
    WHERE session_date = p_session_date
      AND session_id = p_session_id
      AND status = 'checked_in'
    ORDER BY queue_number ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF v_booking_id IS NULL THEN
        RAISE EXCEPTION 'QUEUE_EMPTY';
    END IF;

    -- 3. Update status to called
    UPDATE public.bookings
    SET status = 'called',
        called_at = p_now,
        called_by = p_officer_id,
        updated_at = p_now
    WHERE id = v_booking_id
    RETURNING * INTO v_booking;

    RETURN v_booking;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 4. fn_complete_booking
-- Completes verification, computes final amount based on snapshot price, marks paid
CREATE OR REPLACE FUNCTION public.fn_complete_booking(
    p_booking_id UUID,
    p_officer_id UUID,
    p_verified_qty NUMERIC,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS public.bookings AS $$
DECLARE
    v_booking public.bookings;
    v_final_amount NUMERIC(12,2);
BEGIN
    IF p_verified_qty IS NULL OR p_verified_qty <= 0 THEN
        RAISE EXCEPTION 'INVALID_QUANTITY';
    END IF;

    SELECT * INTO v_booking
    FROM public.bookings
    WHERE id = p_booking_id;

    IF NOT FOUND OR v_booking.status <> 'called' OR v_booking.called_by <> p_officer_id THEN
        RAISE EXCEPTION 'NOT_CALLED';
    END IF;

    v_final_amount := ROUND((p_verified_qty * v_booking.price_per_kg), 2);

    UPDATE public.bookings
    SET status = 'completed',
        verified_quantity_kg = p_verified_qty,
        final_amount = v_final_amount,
        payout_status = 'paid',
        paid_at = p_now,
        completed_at = p_now,
        updated_at = p_now
    WHERE id = p_booking_id
    RETURNING * INTO v_booking;

    RETURN v_booking;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 5. fn_mark_no_show
-- Marks a called customer as no-show
CREATE OR REPLACE FUNCTION public.fn_mark_no_show(
    p_booking_id UUID,
    p_officer_id UUID,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS public.bookings AS $$
DECLARE
    v_booking public.bookings;
BEGIN
    SELECT * INTO v_booking
    FROM public.bookings
    WHERE id = p_booking_id;

    IF NOT FOUND OR v_booking.status <> 'called' OR v_booking.called_by <> p_officer_id THEN
        RAISE EXCEPTION 'NOT_CALLED';
    END IF;

    UPDATE public.bookings
    SET status = 'no_show',
        payout_status = 'not_applicable',
        completed_at = p_now,
        updated_at = p_now
    WHERE id = p_booking_id
    RETURNING * INTO v_booking;

    RETURN v_booking;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 6. fn_cancel_booking
-- Cancels a booking if still in 'booked' state before session start
CREATE OR REPLACE FUNCTION public.fn_cancel_booking(
    p_booking_id UUID,
    p_customer_id UUID,
    p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS public.bookings AS $$
DECLARE
    v_booking public.bookings;
    v_start_time TIME;
    v_start_ts TIMESTAMPTZ;
BEGIN
    SELECT * INTO v_booking
    FROM public.bookings
    WHERE id = p_booking_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'BOOKING_NOT_FOUND';
    END IF;

    IF v_booking.customer_id <> p_customer_id THEN
        RAISE EXCEPTION 'FORBIDDEN';
    END IF;

    IF v_booking.status <> 'booked' THEN
        RAISE EXCEPTION 'CANNOT_CANCEL';
    END IF;

    SELECT start_time INTO v_start_time
    FROM public.session_templates
    WHERE id = v_booking.session_id;

    v_start_ts := ((v_booking.session_date::text || ' ' || v_start_time::text)::timestamp) AT TIME ZONE 'Asia/Kolkata';

    IF p_now >= v_start_ts THEN
        RAISE EXCEPTION 'CANNOT_CANCEL';
    END IF;

    UPDATE public.bookings
    SET status = 'cancelled',
        payout_status = 'not_applicable',
        cancelled_at = p_now,
        updated_at = p_now
    WHERE id = p_booking_id
    RETURNING * INTO v_booking;

    RETURN v_booking;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 7. fn_expire_bookings
-- Runs background expiration:
-- 1. 'booked' with session end passed in IST -> 'missed'
-- 2. 'checked_in' or 'called' from past dates (IST) -> 'no_show'
CREATE OR REPLACE FUNCTION public.fn_expire_bookings(
    p_now TIMESTAMPTZ
)
RETURNS SETOF public.bookings AS $$
DECLARE
    v_today_ist DATE;
BEGIN
    v_today_ist := (p_now AT TIME ZONE 'Asia/Kolkata')::DATE;

    RETURN QUERY
    WITH expired_booked AS (
        UPDATE public.bookings b
        SET status = 'missed',
            payout_status = 'not_applicable',
            updated_at = p_now
        FROM public.session_templates s
        WHERE b.session_id = s.id
          AND b.status = 'booked'
          AND (((b.session_date::text || ' ' || s.end_time::text)::timestamp) AT TIME ZONE 'Asia/Kolkata') < p_now
        RETURNING b.*
    ),
    expired_uncompleted AS (
        UPDATE public.bookings b
        SET status = 'no_show',
            payout_status = 'not_applicable',
            updated_at = p_now
        WHERE b.status IN ('checked_in', 'called')
          AND b.session_date < v_today_ist
        RETURNING b.*
    )
    SELECT * FROM expired_booked
    UNION ALL
    SELECT * FROM expired_uncompleted;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- 8. fn_availability
-- Aggregates booked counts (excluding cancelled) for a date range
CREATE OR REPLACE FUNCTION public.fn_availability(
    p_from DATE,
    p_to DATE
)
RETURNS TABLE (
    session_date DATE,
    session_id SMALLINT,
    booked_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT b.session_date, b.session_id, COUNT(*) AS booked_count
    FROM public.bookings b
    WHERE b.session_date >= p_from
      AND b.session_date <= p_to
      AND b.status <> 'cancelled'
    GROUP BY b.session_date, b.session_id;
END;
$$ LANGUAGE plpgsql STABLE;

