"""Background scheduler loop handling session slot expiration."""
import asyncio
from app.config import settings
from app.clock import now_ist
from app.db import get_db
from app.services.notifications import create_notification


async def run_expiry_daemon():
    """Background task executed every 60 seconds to expire un-scanned bookings and past items."""
    # Skip background daemon if in automated test mode or credentials not yet configured
    if settings.APP_ENV == "test" or "placeholder" in settings.SUPABASE_URL:
        return

    while True:
        try:
            db = get_db()
            current_dt = now_ist().isoformat()
            rpc_res = db.rpc("fn_expire_bookings", {"p_now": current_dt}).execute()
            expired_rows = rpc_res.data or []

            for row in expired_rows:
                customer_id = row.get("customer_id")
                booking_id = row.get("id")
                status = row.get("status")

                if customer_id:
                    cust_res = db.table("profiles").select("email, full_name").eq("id", customer_id).limit(1).execute()
                    if cust_res.data:
                        cust = cust_res.data[0]
                        first_name = cust["full_name"].split()[0]
                        if status == "missed":
                            create_notification(
                                user_id=customer_id,
                                user_email=cust["email"],
                                first_name=first_name,
                                notification_type="missed",
                                title="Slot Expired - Missed Session",
                                message="Your booked produce selling slot has expired because check-in was not completed before session end. You can book a new slot at any time.",
                                booking_id=booking_id,
                                meta={"receipt_no": row.get("receipt_no")}
                            )
                        elif status == "no_show":
                            create_notification(
                                user_id=customer_id,
                                user_email=cust["email"],
                                first_name=first_name,
                                notification_type="missed",
                                title="Slot Marked No-Show",
                                message="Your booking was marked as No-Show because service was not completed.",
                                booking_id=booking_id,
                                meta={"receipt_no": row.get("receipt_no")}
                            )
        except Exception as e:
            # Must handle exceptions without crashing
            print(f"[EXPIRY DAEMON WARNING] Error running expiry loop: {e}")

        # Sleep for 60 seconds before next iteration
        await asyncio.sleep(60)
