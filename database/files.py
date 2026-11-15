"""File catalogue: submissions, approval, channel indexing, search, access control."""
import re
import secrets

from pymongo.errors import DuplicateKeyError

from database import mongo, users
from utils.text import utcnow, normalize_name


def _c():
    return mongo.col(mongo.FILES)


def new_token() -> str:
    return secrets.token_urlsafe(9)


def _search_name(file_name: str | None, caption: str | None) -> str:
    return normalize_name(f"{file_name or ''} {caption or ''}")


async def submit(owner_id: int, media: dict, auto_approve: bool = False):
    """media: file_id, file_unique_id, file_type, file_name, file_size, caption.
    Returns (doc, created). An identical live file (same unique id) is not duplicated."""
    dup = await _c().find_one({"file_unique_id": media["file_unique_id"],
                               "status": {"$in": ["pending", "approved"]}})
    if dup:
        return dup, False
    now = utcnow()
    doc = {"_id": new_token(), **media, "search_name": _search_name(media.get("file_name"), media.get("caption")),
           "owner_id": owner_id, "source": "user", "visibility": "public",
           "status": "approved" if auto_approve else "pending", "created_at": now}
    if auto_approve:
        doc["approved_at"] = now
    await _c().insert_one(doc)
    return doc, True


async def add_channel_file(chat_id: int, message_id: int, media: dict):
    """Index a file posted in a source channel. Returns (doc, created); duplicates are ignored."""
    doc = {"_id": new_token(), **media, "search_name": _search_name(media.get("file_name"), media.get("caption")),
           "source": "channel", "src_key": f"{chat_id}:{message_id}", "chat_id": chat_id,
           "message_id": message_id, "visibility": "public", "status": "approved", "created_at": utcnow()}
    try:
        await _c().insert_one(doc)
    except DuplicateKeyError:
        return await _c().find_one({"src_key": doc["src_key"]}), False
    return doc, True


async def set_caption(token: str, caption_html: str) -> None:
    await _c().update_one({"_id": token}, {"$set": {"caption_html": caption_html}})


async def get(token: str) -> dict | None:
    return await _c().find_one({"_id": token}) if token else None


async def approve(token: str, admin_id: int) -> dict | None:
    return await _c().find_one_and_update({"_id": token, "status": "pending"},
                                          {"$set": {"status": "approved", "approved_by": admin_id,
                                                    "approved_at": utcnow()}}, return_document=True)


async def reject(token: str, admin_id: int) -> dict | None:
    return await _c().find_one_and_update({"_id": token, "status": "pending"},
                                          {"$set": {"status": "rejected", "rejected_by": admin_id,
                                                    "rejected_at": utcnow()}}, return_document=True)


async def delete(token: str) -> bool:
    return (await _c().delete_one({"_id": token})).deleted_count == 1


async def set_visibility(token: str, visibility: str) -> bool:
    return (await _c().update_one({"_id": token}, {"$set": {"visibility": visibility}})).matched_count == 1


async def search(query: str, skip: int = 0, limit: int = 8) -> tuple[list[dict], int]:
    tokens = [t for t in normalize_name(query).split(" ") if t][:6]
    if not tokens:
        return [], 0
    flt = {"status": "approved",
           "$and": [{"search_name": {"$regex": re.escape(t), "$options": "i"}} for t in tokens]}
    total = await _c().count_documents(flt)
    rows = await _c().find(flt).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return rows, total


async def list_by_status(status: str, skip: int = 0, limit: int = 10) -> list[dict]:
    return await _c().find({"status": status}).sort("created_at", 1 if status == "pending" else -1).skip(skip).limit(limit).to_list(limit)


async def list_recent(skip: int = 0, limit: int = 10) -> list[dict]:
    return await _c().find({}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)


async def list_by_owner(owner_id: int, skip: int = 0, limit: int = 8) -> tuple[list[dict], int]:
    flt = {"owner_id": owner_id}
    return (await _c().find(flt).sort("created_at", -1).skip(skip).limit(limit).to_list(limit),
            await _c().count_documents(flt))


async def count(status: str | None = None) -> int:
    return await _c().count_documents({"status": status} if status else {})


def can_access(file: dict | None, user: dict | None, is_admin: bool = False) -> tuple[bool, str]:
    """Access control: file must be approved, user not banned, premium-only files need premium."""
    if not file:
        return False, "no_file"
    if is_admin:
        return True, "ok"
    if not user:
        return False, "no_user"
    if user.get("banned"):
        return False, "banned"
    if file.get("status") != "approved":
        if file.get("owner_id") == user["_id"] and file.get("status") == "pending":
            return False, "pending"
        return False, "no_file"
    if file.get("visibility") == "premium" and not users.is_unlimited(user):
        return False, "premium_only"
    return True, "ok"
