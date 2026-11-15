"""File requests and user feedback."""
import secrets

from database import mongo
from utils.text import utcnow

MAX_PENDING_PER_USER = 3


def _c():
    return mongo.col(mongo.REQUESTS)


async def create(user_id: int, text: str, auto_approve: bool = False):
    """Returns (doc | None, reason). reason: ok | limit"""
    if await _c().count_documents({"user_id": user_id, "status": "pending"}) >= MAX_PENDING_PER_USER:
        return None, "limit"
    doc = {"_id": secrets.token_hex(4), "user_id": user_id, "text": text[:300],
           "status": "approved" if auto_approve else "pending", "created_at": utcnow()}
    await _c().insert_one(doc)
    return doc, "ok"


async def get(rid: str) -> dict | None:
    return await _c().find_one({"_id": rid})


async def decide(rid: str, status: str, admin_id: int) -> dict | None:
    if status not in ("approved", "rejected", "done"):
        raise ValueError(status)
    flt = {"_id": rid, "status": "pending"} if status != "done" else {"_id": rid, "status": "approved"}
    return await _c().find_one_and_update(flt, {"$set": {"status": status, "decided_by": admin_id,
                                                          "decided_at": utcnow()}}, return_document=True)


async def list_status(status: str, skip: int = 0, limit: int = 1) -> list[dict]:
    return await _c().find({"status": status}).sort("created_at", 1).skip(skip).limit(limit).to_list(limit)


async def count(status: str) -> int:
    return await _c().count_documents({"status": status})


async def add_feedback(user_id: int, text: str) -> None:
    await mongo.col(mongo.FEEDBACK).insert_one({"user_id": user_id, "text": text[:1000], "created_at": utcnow()})


async def list_feedback(skip: int = 0, limit: int = 5) -> tuple[list[dict], int]:
    c = mongo.col(mongo.FEEDBACK)
    return await c.find({}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit), await c.count_documents({})
