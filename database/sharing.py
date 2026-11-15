"""Share workflow: one permission is spent the first time a user creates a share link for a file."""
from dataclasses import dataclass

from pymongo.errors import DuplicateKeyError

from database import files, mongo, settings, users
from utils.text import utcnow


@dataclass
class ShareResult:
    ok: bool
    reason: str          # ok | already | disabled | no_file | no_access | pending | limit | banned | no_permission | no_user
    token: str | None = None
    mode: str = ""


async def share_file(user_id: int, token: str, is_admin: bool = False) -> ShareResult:
    if not await settings.get("sharing_enabled") and not is_admin:
        return ShareResult(False, "disabled")
    f = await files.get(token)
    user = await users.get(user_id)
    allowed, why = files.can_access(f, user, is_admin)
    if not allowed:
        return ShareResult(False, why)
    hist = mongo.col(mongo.SHARING)
    try:      # reserve first: unique (user, file) makes repeated/concurrent requests for one file spend once
        await hist.insert_one({"user_id": user_id, "file_token": token, "file_name": f.get("file_name"),
                               "ts": utcnow()})
    except DuplicateKeyError:
        return ShareResult(True, "already", token)
    res = await users.consume_share(user_id)
    if not res.ok:
        await hist.delete_one({"user_id": user_id, "file_token": token})
        return ShareResult(False, res.reason)
    await hist.update_one({"user_id": user_id, "file_token": token}, {"$set": {"mode": res.mode}})
    return ShareResult(True, "ok", token, res.mode)


async def history(user_id: int | None = None, skip: int = 0, limit: int = 10) -> list[dict]:
    flt = {"user_id": user_id} if user_id else {}
    return await mongo.col(mongo.SHARING).find(flt).sort("ts", -1).skip(skip).limit(limit).to_list(limit)


async def count(user_id: int | None = None, since=None) -> int:
    flt: dict = {"user_id": user_id} if user_id else {}
    if since:
        flt["ts"] = {"$gte": since}
    return await mongo.col(mongo.SHARING).count_documents(flt)
