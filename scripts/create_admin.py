"""Bootstrap script to create the initial Super Administrator account."""
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.config import settings
from app.db import get_db


def bootstrap_admin():
    email = settings.ADMIN_EMAIL.strip().lower()
    password = settings.ADMIN_PASSWORD
    full_name = settings.ADMIN_FULL_NAME.strip()

    print(f"Creating Super Administrator account for '{email}'...")

    db = get_db()

    # Check if admin profile already exists
    res = db.table("profiles").select("id, role").eq("email", email).execute()
    if res.data:
        print(f"User with email '{email}' already exists in profiles (Role: {res.data[0]['role']}).")
        return

    # Create user in Supabase Auth
    try:
        auth_res = db.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name, "role": "admin"}
        })
        user_id = auth_res.user.id
        print(f"Created Auth User with ID: {user_id}")
    except Exception as e:
        print(f"Error creating auth user: {e}")
        # If user existed in auth, query user by email
        try:
            users_list = db.auth.admin.list_users()
            matching = [u for u in users_list if u.email == email]
            if matching:
                user_id = matching[0].id
                print(f"Found existing Auth User with ID: {user_id}")
            else:
                return
        except Exception:
            return

    # Insert admin profile
    try:
        db.table("profiles").upsert({
            "id": user_id,
            "role": "admin",
            "full_name": full_name,
            "email": email,
            "is_active": True
        }).execute()
        print(f"Successfully initialized Super Admin profile for '{full_name}' ({email}).")
    except Exception as e:
        print(f"Error creating admin profile: {e}")


if __name__ == "__main__":
    bootstrap_admin()

