"""OPTIONAL Development-Only Demo Seeder.

DO NOT RUN IN PRODUCTION.
Creates demo staff (scanner, officer) and a demo farmer for local testing.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db import get_db

DEMO_USERS = [
    {
        "email": "scanner@slotbooking.gov.in",
        "password": "ScannerPass123!",
        "full_name": "Gate Staff Raman",
        "role": "scanner"
    },
    {
        "email": "officer@slotbooking.gov.in",
        "password": "OfficerPass123!",
        "full_name": "Desk Officer Priya",
        "role": "officer"
    },
    {
        "email": "farmer@example.com",
        "password": "FarmerPass123!",
        "full_name": "Murugan K",
        "role": "customer",
        "mobile": "9876543210",
        "dob": "1988-06-15",
        "gender": "male",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "address": "124 South Street, Pollachi"
    }
]


def seed_demo_accounts():
    db = get_db()
    print("=== SEEDING DEVELOPMENT DEMO ACCOUNTS ===")

    for u in DEMO_USERS:
        email = u["email"]
        role = u["role"]
        full_name = u["full_name"]

        # Check existing profile
        res = db.table("profiles").select("id").eq("email", email).execute()
        if res.data:
            print(f"[-] Profile for {email} already exists. Skipping.")
            continue

        try:
            auth_res = db.auth.admin.create_user({
                "email": email,
                "password": u["password"],
                "email_confirm": True,
                "user_metadata": {"full_name": full_name, "role": role}
            })
            user_id = auth_res.user.id
        except Exception as e:
            print(f"[!] Auth creation notice for {email}: {e}")
            try:
                users = db.auth.admin.list_users()
                matching = [x for x in users if x.email == email]
                if matching:
                    user_id = matching[0].id
                else:
                    continue
            except Exception:
                continue

        profile_payload = {
            "id": user_id,
            "role": role,
            "full_name": full_name,
            "email": email,
            "is_active": True
        }
        if role == "customer":
            profile_payload.update({
                "mobile": u["mobile"],
                "dob": u["dob"],
                "gender": u["gender"],
                "state": u["state"],
                "district": u["district"],
                "address": u["address"]
            })

        db.table("profiles").upsert(profile_payload).execute()
        print(f"[+] Created demo {role}: {email} / {u['password']}")

    print("=== DEMO SEEDING COMPLETED ===")


if __name__ == "__main__":
    seed_demo_accounts()

