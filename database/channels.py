"""Channels used as caption sources ('source') or force-subscribe requirements ('fsub')."""
from database import mongo
from utils.text import utcnow


def _c():
    return mongo.col(mongo.CHANNELS)


def _key(role: str, chat_id: int) -> str:
    return f"{role}:{chat_id}"


async def add(role: str, chat_id: int, title: str = "", username: str | None = None,
              invite_link: str | None = None, private: bool = False) -> bool:
    r = await _c().update_one({"_id": _key(role, chat_id)},
                              {"$set": {"role": role, "chat_id": chat_id, "title": title or str(chat_id),
                                        "username": username or "", "invite_link": invite_link or "",
                                        "private": private},
                               "$setOnInsert": {"added_at": utcnow()}}, upsert=True)
    return r.upserted_id is not None


async def remove(role: str, chat_id: int) -> bool:
    return (await _c().delete_one({"_id": _key(role, chat_id)})).deleted_count == 1


async def get(role: str, chat_id: int) -> dict | None:
    return await _c().find_one({"_id": _key(role, chat_id)})


async def list_role(role: str) -> list[dict]:
    return await _c().find({"role": role}).sort("added_at", 1).to_list(None)


async def set_invite(role: str, chat_id: int, link: str) -> bool:
    return (await _c().update_one({"_id": _key(role, chat_id)}, {"$set": {"invite_link": link}})).matched_count == 1


def join_url(ch: dict) -> str | None:
    if ch.get("invite_link"):
        return ch["invite_link"]
    if ch.get("username"):
        return f"https://t.me/{ch['username']}"
    return None
