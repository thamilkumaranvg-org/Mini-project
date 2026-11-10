"""Test configuration, mock database fixtures, and test client setup."""
import os
import sys
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import pytest

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment variables for tests
os.environ["APP_ENV"] = "test"
os.environ["SUPABASE_URL"] = "https://mock-test.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "mock_anon_key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "mock_service_role_key"
os.environ["TIMEZONE"] = "Asia/Kolkata"
os.environ["EMAIL_PROVIDER"] = "console"

