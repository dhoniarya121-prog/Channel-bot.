"""Admin roster and fine-grained permissions. Owners (OWNER_ID env) hold every permission."""
import time

import config
from database import mongo
from utils.text import utcnow

PERMS = ["users", "files", "sharing", "premium", "referrals", "captions", "channels", "forcesub",
         "broadcast", "stats", "security", "maintenance", "backup", "logs", "system"]
DEFAULT_PERMS = ["users", "files", "sharing", "premium", "referrals", "stats", "logs"]
OWNER_ONLY = "owner"      # pseudo permission: only owners (admin management)

_cache: dict = {"ts": float("-inf"), "ids": set()}


def _c():
    return mongo.col(mongo.ADMINS)


def is_owner(uid: int) -> bool:
    return uid in config.OWNER_IDS


def invalidate() -> None:
    _cache["ts"] = float("-inf")


async def _ids() -> set[int]:
    if time.monotonic() - _cache["ts"] > 30:
        _cache["ids"] = {d["_id"] for d in await _c().find({}, {"_id": 1}).to_list(None)}
        _cache["ts"] = time.monotonic()
    return _cache["ids"]


async def is_admin(uid: int) -> bool:
    return is_owner(uid) or uid in await _ids()


async def has_perm(uid: int, perm: str | None) -> bool:
    if is_owner(uid):
        return True
    if perm == OWNER_ONLY:
        return False
    if not await is_admin(uid):
        return False
    if perm is None:
        return True
    doc = await _c().find_one({"_id": uid})
    return bool(doc and perm in doc.get("perms", []))


async def get(uid: int) -> dict | None:
    return await _c().find_one({"_id": uid})


async def add(uid: int, by: int, perms: list[str] | None = None) -> bool:
    r = await _c().update_one({"_id": uid}, {"$setOnInsert": {"perms": list(perms or DEFAULT_PERMS),
                                                              "added_by": by, "added_at": utcnow()}}, upsert=True)
    invalidate()
    return r.upserted_id is not None


async def remove(uid: int) -> bool:
    r = await _c().delete_one({"_id": uid})
    invalidate()
    return r.deleted_count == 1


async def toggle_perm(uid: int, perm: str) -> bool | None:
    if perm not in PERMS:
        return None
    doc = await get(uid)
    if not doc:
        return None
    if perm in doc.get("perms", []):
        await _c().update_one({"_id": uid}, {"$set": {"perms": [p for p in doc["perms"] if p != perm]}})
        return False
    await _c().update_one({"_id": uid}, {"$set": {"perms": doc.get("perms", []) + [perm]}})
    return True


async def list_all() -> list[dict]:
    return await _c().find({}).sort("added_at", 1).to_list(None)


async def all_ids() -> set[int]:
    return set(config.OWNER_IDS) | await _ids()
