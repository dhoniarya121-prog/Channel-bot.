"""MongoDB connection (Motor), collection names and index creation."""
import logging
import time

log = logging.getLogger(__name__)

USERS, FILES, SHARING, PREMIUM = "users", "files", "sharing_history", "premium_users"
REFERRALS, ADMINS, SETTINGS, CHANNELS = "referrals", "admins", "settings", "channels"
REQUESTS, BROADCASTS, LOGS, FEEDBACK = "requests", "broadcasts", "logs", "feedback"
ALL_COLLECTIONS = [USERS, FILES, SHARING, PREMIUM, REFERRALS, ADMINS, SETTINGS, CHANNELS,
                   REQUESTS, BROADCASTS, LOGS, FEEDBACK]

LOG_TTL_SECONDS = 30 * 86400

INDEXES = [
    (USERS, [("ref_code", 1)], dict(unique=True, sparse=True)),
    (USERS, [("username_l", 1)], {}),
    (USERS, [("premium_until", 1)], {}),
    (USERS, [("joined_at", -1)], {}),
    (USERS, [("last_active", -1)], {}),
    (FILES, [("src_key", 1)], dict(unique=True, sparse=True)),
    (FILES, [("status", 1), ("created_at", -1)], {}),
    (FILES, [("owner_id", 1), ("created_at", -1)], {}),
    (FILES, [("file_unique_id", 1)], {}),
    (SHARING, [("user_id", 1), ("file_token", 1)], dict(unique=True)),
    (SHARING, [("ts", -1)], {}),
    (PREMIUM, [("end", 1)], {}),
    (REFERRALS, [("referrer_id", 1), ("created_at", -1)], {}),
    (CHANNELS, [("role", 1)], {}),
    (REQUESTS, [("status", 1), ("created_at", -1)], {}),
    (REQUESTS, [("user_id", 1)], {}),
    (BROADCASTS, [("created_at", -1)], {}),
    (LOGS, [("ts", 1)], dict(expireAfterSeconds=LOG_TTL_SECONDS)),
    (LOGS, [("kind", 1), ("user_id", 1), ("ts", -1)], {}),
    (FEEDBACK, [("created_at", -1)], {}),
]


class _State:
    client = None
    db = None


_s = _State()


def use(db) -> None:
    """Inject a database object (used by tests)."""
    _s.db = db


def col(name: str):
    if _s.db is None:
        raise RuntimeError("Database is not initialised")
    return _s.db[name]


async def connect(uri: str, name: str) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient
    _s.client = AsyncIOMotorClient(uri, tz_aware=True, serverSelectionTimeoutMS=15000,
                                   appname="roaroic-autolink")
    _s.db = _s.client[name]
    await ping()
    await ensure_indexes()
    log.info("MongoDB connected (db=%s)", name)


async def ensure_indexes() -> None:
    for cname, keys, kw in INDEXES:
        await col(cname).create_index(keys, **kw)


async def ping() -> float:
    t = time.perf_counter()
    await _s.db.command("ping")
    return (time.perf_counter() - t) * 1000


async def close() -> None:
    if _s.client is not None:
        _s.client.close()
        _s.client = None
