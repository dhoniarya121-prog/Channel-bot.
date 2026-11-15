"""Users: registration, ban/warn/verify, per-user permissions and ATOMIC share quota."""
import re
from dataclasses import dataclass
from datetime import timedelta

from pymongo.errors import DuplicateKeyError

from database import mongo, settings
from utils.text import utcnow, as_aware

DEFAULT_PERMS = {"share": True, "submit": True, "request": True, "feedback": True}


def _c():
    return mongo.col(mongo.USERS)


@dataclass
class Consume:
    ok: bool
    reason: str          # ok | no_user | banned | no_permission | limit
    mode: str = ""       # unlimited | quota


def is_premium(doc: dict | None, now=None) -> bool:
    until = as_aware((doc or {}).get("premium_until"))
    return bool(until and until > (now or utcnow()))


def is_unlimited(doc: dict | None, now=None) -> bool:
    return bool(doc and (doc.get("unlimited") or is_premium(doc, now)))


def has_perm(doc: dict | None, perm: str) -> bool:
    return (doc or {}).get("perms", {}).get(perm, True) is not False


async def register(user_id: int, first_name: str = "", username: str | None = None,
                   lang_code: str | None = None):
    """Idempotent. Returns (doc, created)."""
    now = utcnow()
    quota = await settings.get("free_quota")
    lang = "hi" if (lang_code or "").lower().startswith("hi") else "en"
    update = {
        "$setOnInsert": {"joined_at": now, "banned": False, "warns": 0, "verified": False,
                         "plan": "free", "quota_remaining": quota, "unlimited": False,
                         "shared_total": 0, "referral_count": 0, "perms": dict(DEFAULT_PERMS),
                         "lang": lang},
        "$set": {"first_name": first_name or "", "username": username or "",
                 "username_l": (username or "").lower(), "last_active": now},
    }
    for attempt in (1, 2):
        try:
            res = await _c().update_one({"_id": user_id}, update, upsert=True)
            break
        except DuplicateKeyError:           # concurrent first message -> retry as update
            if attempt == 2:
                raise
    return await get(user_id), res.upserted_id is not None


async def get(user_id: int) -> dict | None:
    return await _c().find_one({"_id": user_id})


async def find(query: str) -> dict | None:
    q = (query or "").strip().lstrip("@")
    if q.lstrip("-").isdigit():
        return await get(int(q))
    if re.fullmatch(r"[A-Za-z0-9_]{3,32}", q):
        return await _c().find_one({"username_l": q.lower()})
    return None


async def find_by_ref_code(code: str) -> dict | None:
    return await _c().find_one({"ref_code": code}) if code else None


async def set_lang(user_id: int, lang: str) -> None:
    await _c().update_one({"_id": user_id}, {"$set": {"lang": lang}})


async def ban(user_id: int, reason: str = "", by: int | None = None) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$set": {"banned": True, "ban_reason": reason,
                                                          "banned_by": by, "banned_at": utcnow()}})
    return r.matched_count == 1


async def unban(user_id: int) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$set": {"banned": False, "warns": 0},
                                                 "$unset": {"ban_reason": "", "banned_by": ""}})
    return r.matched_count == 1


async def warn(user_id: int, by: int | None, reason: str, max_warns: int):
    """Returns (warns, auto_banned) or None when user missing."""
    doc = await _c().find_one_and_update(
        {"_id": user_id},
        {"$inc": {"warns": 1}, "$push": {"warn_log": {"by": by, "reason": reason[:200], "at": utcnow()}}},
        return_document=True)
    if not doc:
        return None
    if doc["warns"] >= max_warns and not doc.get("banned"):
        await ban(user_id, f"Auto-ban: {doc['warns']} warnings", by)
        return doc["warns"], True
    return doc["warns"], False


async def clear_warns(user_id: int) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$set": {"warns": 0, "warn_log": []}})
    return r.matched_count == 1


async def set_verified(user_id: int, value: bool = True) -> bool:
    """True only when the state actually changed (used to reward referrals exactly once)."""
    flt = {"_id": user_id, "verified": {"$ne": True}} if value else {"_id": user_id, "verified": True}
    r = await _c().update_one(flt, {"$set": {"verified": value, "verified_at": utcnow()}})
    return r.modified_count == 1


async def set_permission(user_id: int, perm: str, allowed: bool) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$set": {f"perms.{perm}": allowed}})
    return r.matched_count == 1


# ---------------------------------------------------------------- quota
async def consume_share(user_id: int) -> Consume:
    """Atomically spend one share permission. Each step is ONE conditional update, so concurrent
    requests can never spend the same permission twice."""
    now = utcnow()
    base = {"_id": user_id, "banned": {"$ne": True}, "perms.share": {"$ne": False}}
    r = await _c().update_one(
        {**base, "$or": [{"unlimited": True}, {"premium_until": {"$gt": now}}]},
        {"$inc": {"shared_total": 1}, "$set": {"last_share_at": now}})
    if r.matched_count:
        return Consume(True, "ok", "unlimited")
    r = await _c().update_one(
        {**base, "quota_remaining": {"$gt": 0}},
        {"$inc": {"quota_remaining": -1, "shared_total": 1}, "$set": {"last_share_at": now}})
    if r.matched_count:
        return Consume(True, "ok", "quota")
    doc = await get(user_id)
    if not doc:
        return Consume(False, "no_user")
    if doc.get("banned"):
        return Consume(False, "banned")
    if not has_perm(doc, "share"):
        return Consume(False, "no_permission")
    return Consume(False, "limit")


async def refund_share(user_id: int, mode: str) -> None:
    if mode == "quota":
        await _c().update_one({"_id": user_id}, {"$inc": {"quota_remaining": 1, "shared_total": -1}})
    elif mode == "unlimited":
        await _c().update_one({"_id": user_id}, {"$inc": {"shared_total": -1}})


async def set_quota(user_id: int, n: int) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$set": {"quota_remaining": max(0, n)}})
    return r.matched_count == 1


async def add_quota(user_id: int, n: int) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$inc": {"quota_remaining": n}})
    return r.matched_count == 1


async def reset_quota(user_id: int) -> int | None:
    n = await settings.get("free_quota")
    r = await _c().update_one({"_id": user_id}, {"$set": {"quota_remaining": n}})
    return n if r.matched_count else None


async def set_unlimited(user_id: int, value: bool) -> bool:
    r = await _c().update_one({"_id": user_id}, {"$set": {"unlimited": value}})
    return r.matched_count == 1


async def reset_all_free_quota() -> int:
    n = await settings.get("free_quota")
    r = await _c().update_many({"unlimited": {"$ne": True}}, {"$set": {"quota_remaining": n}})
    return r.matched_count


# ---------------------------------------------------------------- lists / stats
async def list_users(skip: int = 0, limit: int = 10, flt: dict | None = None) -> list[dict]:
    return await _c().find(flt or {}).sort("joined_at", -1).skip(skip).limit(limit).to_list(limit)


async def count(flt: dict | None = None) -> int:
    return await _c().count_documents(flt or {})


async def mark_blocked(user_id: int, value: bool = True) -> None:
    await _c().update_one({"_id": user_id}, {"$set": {"blocked": value}})


async def audience(group: str) -> list[int]:
    now = utcnow()
    flt: dict = {"banned": {"$ne": True}, "blocked": {"$ne": True}}
    if group == "premium":
        flt["premium_until"] = {"$gt": now}
    elif group == "free":
        flt["$or"] = [{"premium_until": {"$exists": False}}, {"premium_until": {"$lte": now}}]
    elif group == "verified":
        flt["verified"] = True
    elif group == "active7d":
        flt["last_active"] = {"$gte": now - timedelta(days=7)}
    elif group == "new7d":
        flt["joined_at"] = {"$gte": now - timedelta(days=7)}
    elif group != "all":
        raise ValueError(f"unknown audience {group!r}")
    docs = await _c().find(flt, {"_id": 1}).to_list(None)
    return [d["_id"] for d in docs]


AUDIENCES = ("all", "premium", "free", "verified", "active7d", "new7d")


async def stats() -> dict:
    now = utcnow()
    d1, d7 = now - timedelta(days=1), now - timedelta(days=7)
    return {
        "total": await count(),
        "premium": await count({"premium_until": {"$gt": now}}),
        "banned": await count({"banned": True}),
        "blocked": await count({"blocked": True}),
        "verified": await count({"verified": True}),
        "new_24h": await count({"joined_at": {"$gte": d1}}),
        "new_7d": await count({"joined_at": {"$gte": d7}}),
        "active_24h": await count({"last_active": {"$gte": d1}}),
        "active_7d": await count({"last_active": {"$gte": d7}}),
    }
