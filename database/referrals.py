"""Referral tracking with abuse protection. One referral row per referred user (_id = referred id)."""
import secrets
from dataclasses import dataclass
from datetime import timedelta

from pymongo.errors import DuplicateKeyError

from database import mongo, premium, settings, users
from utils.text import utcnow


@dataclass
class TrackResult:
    status: str   # ok | disabled | invalid_code | self | already_referred | referrer_banned | cap_reached
    referrer_id: int | None = None


async def ensure_code(user_id: int) -> str | None:
    c = mongo.col(mongo.USERS)
    doc = await c.find_one({"_id": user_id})
    if not doc:
        return None
    if doc.get("ref_code"):
        return doc["ref_code"]
    for _ in range(5):
        code = secrets.token_urlsafe(6).replace("-", "a").replace("_", "b")[:8]
        try:
            r = await c.update_one({"_id": user_id, "ref_code": {"$exists": False}}, {"$set": {"ref_code": code}})
        except DuplicateKeyError:
            continue
        if r.matched_count:
            return code
        return (await c.find_one({"_id": user_id})).get("ref_code")
    raise RuntimeError("could not allocate referral code")


async def track(referred_id: int, code: str) -> TrackResult:
    """Call ONLY for a brand-new user arriving through a referral link."""
    if not await settings.get("referral_enabled"):
        return TrackResult("disabled")
    referrer = await users.find_by_ref_code(code)
    if not referrer:
        return TrackResult("invalid_code")
    rid = referrer["_id"]
    if rid == referred_id:
        return TrackResult("self", rid)
    if referrer.get("banned"):
        return TrackResult("referrer_banned", rid)
    cap = await settings.get("referral_daily_cap")
    since = utcnow() - timedelta(hours=24)
    if cap and await mongo.col(mongo.REFERRALS).count_documents(
            {"referrer_id": rid, "created_at": {"$gte": since}}) >= cap:
        return TrackResult("cap_reached", rid)
    try:
        await mongo.col(mongo.REFERRALS).insert_one(
            {"_id": referred_id, "referrer_id": rid, "status": "pending", "created_at": utcnow()})
    except DuplicateKeyError:
        return TrackResult("already_referred", rid)
    await mongo.col(mongo.USERS).update_one({"_id": referred_id, "referred_by": {"$exists": False}},
                                            {"$set": {"referred_by": rid}})
    return TrackResult("ok", rid)


async def reward_on_verify(referred_id: int) -> dict | None:
    """Reward the referrer exactly once, after the referred user verified."""
    row = await mongo.col(mongo.REFERRALS).find_one_and_update(
        {"_id": referred_id, "status": "pending"},
        {"$set": {"status": "rewarded", "rewarded_at": utcnow()}}, return_document=True)
    if not row:
        return None
    rid = row["referrer_id"]
    referrer = await users.get(rid)
    if not referrer or referrer.get("banned"):
        await mongo.col(mongo.REFERRALS).update_one({"_id": referred_id}, {"$set": {"status": "rejected"}})
        return None
    quota = int(await settings.get("referral_reward_quota") or 0)
    days = int(await settings.get("referral_reward_premium_days") or 0)
    mode = await settings.get("quota_mode")
    if quota:
        await (users.add_daily_bonus(rid, quota) if mode == "daily" else users.add_quota(rid, quota))
    if days:
        await premium.activate(rid, days, None)
    await mongo.col(mongo.USERS).update_one({"_id": rid}, {"$inc": {"referral_count": 1}})
    return {"referrer_id": rid, "quota": quota, "days": days, "mode": mode}


async def stats(user_id: int) -> dict:
    c = mongo.col(mongo.REFERRALS)
    return {"total": await c.count_documents({"referrer_id": user_id}),
            "rewarded": await c.count_documents({"referrer_id": user_id, "status": "rewarded"}),
            "pending": await c.count_documents({"referrer_id": user_id, "status": "pending"})}


async def top(limit: int = 10) -> list[dict]:
    return await mongo.col(mongo.USERS).find({"referral_count": {"$gt": 0}}).sort(
        "referral_count", -1).limit(limit).to_list(limit)
