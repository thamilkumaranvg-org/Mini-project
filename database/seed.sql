-- ======================================================================
-- Farmer Slot Booking System: Database Seed Data
-- Idempotent inserts for session templates and initial crop catalog
-- ======================================================================

-- 1. SEED SESSION TEMPLATES (Fixed daily sessions, Asia/Kolkata)
INSERT INTO public.session_templates (id, name, start_time, end_time, capacity)
VALUES
    (1, 'Session 1', '09:00:00', '11:00:00', 8),
    (2, 'Session 2', '11:20:00', '13:20:00', 8),
    (3, 'Session 3', '14:00:00', '16:00:00', 8)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    capacity = EXCLUDED.capacity;

-- 2. SEED CROPS
-- NOTE: Prices below are ILLUSTRATIVE PLACEHOLDER prices (replace with official MSP/market prices as needed).
INSERT INTO public.crops (name, emoji, price_per_kg, is_active)
VALUES
    ('Paddy (Dhan)', '🌾', 23.00, true),
    ('Wheat (Gehun)', '🌾', 24.25, true),
    ('Maize (Makka)', '🌽', 22.50, true),
    ('Ragi (Finger Millet)', '🥣', 38.50, true),
    ('Bajra (Cumbu / Pearl Millet)', '🌾', 26.25, true),
    ('Jowar (Sorghum)', '🌾', 33.75, true),
    ('Groundnut (Peanut)', '🥜', 67.80, true),
    ('Cotton', '⚪', 71.20, true),
    ('Turmeric', '🟡', 95.00, true),
    ('Black gram (Urad)', '⚫', 74.00, true),
    ('Green gram (Moong)', '🟢', 86.50, true),
    ('Sugarcane', '🎋', 3.40, true)
ON CONFLICT (name) DO UPDATE SET
    emoji = EXCLUDED.emoji,
    price_per_kg = EXCLUDED.price_per_kg,
    is_active = EXCLUDED.is_active;

