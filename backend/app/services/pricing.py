"""Crop price management, historical price audits, and active crop catalog."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db import get_db
from app.errors import BadRequest, NotFound
from app.security import record_audit
from app.schemas import CropResponse, AdminCropItem


def get_active_crops() -> List[CropResponse]:
    """Retrieve all active crops for farmer slot booking."""
    db = get_db()
    res = db.table("crops").select("id, name, emoji, price_per_kg, is_active").eq("is_active", True).order("name").execute()
    return [
        CropResponse(
            id=r["id"],
            name=r["name"],
            emoji=r.get("emoji"),
            price_per_kg=float(r["price_per_kg"]),
            is_active=r["is_active"]
        ) for r in (res.data or [])
    ]


def get_all_crops_admin() -> List[AdminCropItem]:
    """Admin view of all crops including inactive items."""
    db = get_db()
    res = db.table("crops").select("*").order("name").execute()
    return [
        AdminCropItem(
            id=r["id"],
            name=r["name"],
            emoji=r.get("emoji"),
            price_per_kg=float(r["price_per_kg"]),
            is_active=r["is_active"],
            updated_at=r["updated_at"]
        ) for r in (res.data or [])
    ]


def create_crop(admin_id: str, name: str, emoji: Optional[str], price_per_kg: float) -> AdminCropItem:
    """Create a new crop in the catalog."""
    db = get_db()
    res = db.table("crops").insert({
        "name": name.strip(),
        "emoji": emoji.strip() if emoji else None,
        "price_per_kg": round(price_per_kg, 2),
        "is_active": True,
        "updated_by": admin_id
    }).execute()

    if not res.data:
        raise BadRequest("CREATE_FAILED", "Failed to create crop.")

    new_crop = res.data[0]
    record_audit(
        actor_id=admin_id,
        action="CREATE_CROP",
        entity="crops",
        entity_id=str(new_crop["id"]),
        details={"name": name, "price_per_kg": price_per_kg}
    )

    return AdminCropItem(
        id=new_crop["id"],
        name=new_crop["name"],
        emoji=new_crop.get("emoji"),
        price_per_kg=float(new_crop["price_per_kg"]),
        is_active=new_crop["is_active"],
        updated_at=new_crop["updated_at"]
    )


def update_crop(admin_id: str, crop_id: int, name: Optional[str], emoji: Optional[str], price_per_kg: Optional[float], is_active: Optional[bool]) -> AdminCropItem:
    """Update crop details, recording price alterations in crop_price_history."""
    db = get_db()
    existing_res = db.table("crops").select("*").eq("id", crop_id).limit(1).execute()
    if not existing_res.data:
        raise NotFound("CROP_NOT_FOUND", "Crop not found.")

    current = existing_res.data[0]
    old_price = float(current["price_per_kg"])

    update_payload: Dict[str, Any] = {"updated_by": admin_id}
    if name is not None:
        update_payload["name"] = name.strip()
    if emoji is not None:
        update_payload["emoji"] = emoji.strip()
    if is_active is not None:
        update_payload["is_active"] = is_active

    price_changed = False
    if price_per_kg is not None:
        new_price = round(price_per_kg, 2)
        if new_price != old_price:
            update_payload["price_per_kg"] = new_price
            price_changed = True

    res = db.table("crops").update(update_payload).eq("id", crop_id).execute()
    updated = res.data[0]

    # Record price change in crop_price_history if price changed
    if price_changed:
        db.table("crop_price_history").insert({
            "crop_id": crop_id,
            "old_price": old_price,
            "new_price": update_payload["price_per_kg"],
            "changed_by": admin_id
        }).execute()

    record_audit(
        actor_id=admin_id,
        action="UPDATE_CROP",
        entity="crops",
        entity_id=str(crop_id),
        details={"old_price": old_price, "updated": update_payload}
    )

    return AdminCropItem(
        id=updated["id"],
        name=updated["name"],
        emoji=updated.get("emoji"),
        price_per_kg=float(updated["price_per_kg"]),
        is_active=updated["is_active"],
        updated_at=updated["updated_at"]
    )

