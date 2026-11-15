"""Error/activity logs (TTL index removes entries after 30 days)."""
from database import mongo
from utils.text import utcnow, trunc


def _c():
    return mongo.col(mongo.LOGS)


async def write(level: str, module: str, message: str) -> None:
    await _c().insert_one({"kind": "log", "level": level, "module": module,
                           "message": trunc(message, 3500), "ts": utcnow()})


async def activity(user_id: int, action: str, detail: str = "") -> None:
    await _c().insert_one({"kind": "activity", "user_id": user_id, "action": action,
                           "detail": trunc(detail, 200), "ts": utcnow()})


async def recent(errors_only: bool = False, skip: int = 0, limit: int = 5) -> tuple[list[dict], int]:
    flt: dict = {"kind": "log"}
    if errors_only:
        flt["level"] = {"$in": ["ERROR", "CRITICAL"]}
    return (await _c().find(flt).sort("ts", -1).skip(skip).limit(limit).to_list(limit),
            await _c().count_documents(flt))


async def user_activity(user_id: int | None = None, skip: int = 0, limit: int = 10) -> tuple[list[dict], int]:
    flt: dict = {"kind": "activity"}
    if user_id:
        flt["user_id"] = user_id
    return (await _c().find(flt).sort("ts", -1).skip(skip).limit(limit).to_list(limit),
            await _c().count_documents(flt))


async def clear() -> int:
    return (await _c().delete_many({"kind": "log"})).deleted_count
