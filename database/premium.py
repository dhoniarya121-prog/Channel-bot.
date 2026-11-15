"""Premium plans: activation, renewal, expiry, expiry notices."""
from datetime import timedelta

from database import mongo
from utils.text import utcnow, as_aware

PRESET_DAYS = (7, 30, 90)
MAX_DAYS = 3650


def _u():
    return mongo.col(mongo.USERS)


def _p():
    return mongo.col(mongo.PREMIUM)


async def activate(user_id: int, days: int, admin_id: int | None = None):
    """Grant or renew premium. Renewal extends from the current end date. Returns new end or None."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError("days out of range")
    user = await _u().find_one({"_id": user_id})
    if not user:
        return None
    now = utcnow()
    cur = as_aware(user.get("premium_until"))
    start = cur if cur and cur > now else now
    end = start + timedelta(days=days)
    await _u().update_one({"_id": user_id}, {"$set": {"premium_until": end, "plan": "premium"}})
    await _p().update_one(
        {"_id": user_id},
        {"$set": {"user_id": user_id, "end": end, "active": True, "notified": [], "granted_by": admin_id},
         "$setOnInsert": {"start": now},
         "$inc": {"total_days": days, "renewals": 1 if (cur and cur > now) else 0},
         "$push": {"history": {"days": days, "by": admin_id, "at": now}}},
        upsert=True)
    return end


async def revoke(user_id: int) -> bool:
    r = await _u().update_one({"_id": user_id}, {"$set": {"plan": "free"}, "$unset": {"premium_until": ""}})
    await _p().update_one({"_id": user_id}, {"$set": {"active": False, "end": utcnow()}})
    return r.matched_count == 1


async def status(user_id: int) -> dict:
    user = await _u().find_one({"_id": user_id}) or {}
    until = as_aware(user.get("premium_until"))
    active = bool(until and until > utcnow())
    return {"active": active, "until": until if active else None,
            "unlimited": bool(user.get("unlimited")) or active}


async def expire_due(now=None) -> list[int]:
    """Downgrade users whose premium ended. Returns the ids that were downgraded just now."""
    now = now or utcnow()
    due = await _u().find({"plan": "premium", "premium_until": {"$lte": now}}, {"_id": 1}).to_list(None)
    done = []
    for d in due:
        r = await _u().update_one({"_id": d["_id"], "plan": "premium", "premium_until": {"$lte": now}},
                                  {"$set": {"plan": "free"}})
        if r.matched_count:
            await _p().update_one({"_id": d["_id"]}, {"$set": {"active": False}})
            done.append(d["_id"])
    return done


async def due_for_notice(notify_days: list[int], now=None) -> list[tuple[int, int, object]]:
    """Claims (atomically) at most one pending reminder per user -> [(user_id, days_left_bucket, end)]."""
    now = now or utcnow()
    out = []
    horizon = now + timedelta(days=max(notify_days or [0]))
    docs = await _p().find({"active": True, "end": {"$gt": now, "$lte": horizon}}).to_list(None)
    for d in docs:
        left = as_aware(d["end"]) - now
        bucket = next((n for n in sorted(notify_days) if left <= timedelta(days=n)), None)
        if bucket is None:
            continue
        r = await _p().update_one({"_id": d["_id"], "notified": {"$ne": bucket}},
                                  {"$addToSet": {"notified": bucket}})
        if r.matched_count:
            out.append((d["_id"], bucket, d["end"]))
    return out


async def list_active(skip: int = 0, limit: int = 10) -> list[dict]:
    return await _p().find({"active": True, "end": {"$gt": utcnow()}}).sort("end", 1).skip(skip).limit(limit).to_list(limit)


async def count_active() -> int:
    return await _p().count_documents({"active": True, "end": {"$gt": utcnow()}})
