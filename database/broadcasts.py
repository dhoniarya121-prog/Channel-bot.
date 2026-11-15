from database import mongo
from utils.text import utcnow
import secrets


def _c():
    return mongo.col(mongo.BROADCASTS)


async def create(admin_id: int, audience: str, from_chat: int, message_id: int, total: int) -> dict:
    doc = {"_id": secrets.token_hex(4), "admin_id": admin_id, "audience": audience, "from_chat": from_chat,
           "message_id": message_id, "total": total, "sent": 0, "failed": 0, "blocked": 0,
           "status": "pending", "created_at": utcnow()}
    await _c().insert_one(doc)
    return doc


async def get(bid: str) -> dict | None:
    return await _c().find_one({"_id": bid})


async def claim_start(bid: str) -> dict | None:
    """Only one 'start' click can win (duplicate callbacks cannot launch two broadcasts)."""
    return await _c().find_one_and_update({"_id": bid, "status": "pending"},
                                          {"$set": {"status": "running", "started_at": utcnow()}},
                                          return_document=True)


async def progress(bid: str, sent: int, failed: int, blocked: int) -> None:
    await _c().update_one({"_id": bid}, {"$set": {"sent": sent, "failed": failed, "blocked": blocked}})


async def finish(bid: str, status: str, sent: int, failed: int, blocked: int) -> None:
    await _c().update_one({"_id": bid}, {"$set": {"status": status, "sent": sent, "failed": failed,
                                                  "blocked": blocked, "finished_at": utcnow()}})


async def recent(limit: int = 5) -> list[dict]:
    return await _c().find({}).sort("created_at", -1).limit(limit).to_list(limit)
