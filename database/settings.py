"""Settings persisted in MongoDB (one document per key) with a write-through cache."""
import copy

from database import mongo
from utils.captions import DEFAULT_TEMPLATE, MINIMAL_TEMPLATE, QUOTE_TEMPLATE

DEFAULTS: dict = {
    "quota_mode": "daily",            # "daily" = N files/day (+bonus per referral) | "total" = one-time pool
    "daily_limit": 2,
    "day_reset_offset_min": 330,      # daily reset at local midnight; 330 = IST (UTC+5:30)
    "protect_content": False,         # True = delivered files cannot be forwarded/saved at all
    "free_quota": 5,
    "sharing_enabled": True,
    "auto_caption": True,
    "caption_templates": {"default": DEFAULT_TEMPLATE, "minimal": MINIMAL_TEMPLATE, "quote": QUOTE_TEMPLATE},
    "active_template": "default",
    "links": {"main_channel": "", "backup_channel": "", "movie_bot": "", "discussion_group": ""},
    "old_links": [],
    "channel_buttons": [],
    "buttons_enabled": False,
    "buttons_per_row": 1,
    "forcesub_enabled": False,
    "maintenance": False,
    "maintenance_msg": "🛠 The bot is under maintenance. Please try again later.",
    "antispam": True,
    "rate_limit_count": 8,
    "rate_limit_window": 10,
    "spam_mute_seconds": 60,
    "require_verification": True,
    "max_warns": 3,
    "referral_enabled": True,
    "referral_reward_quota": 2,
    "referral_reward_premium_days": 0,
    "referral_daily_cap": 20,
    "auto_approve_files": False,
    "auto_approve_requests": False,
    "requests_enabled": True,
    "feedback_enabled": True,
    "search_enabled": True,
    "start_message": {"en": "", "hi": ""},
    "premium_notify": True,
    "notify_days": [3, 1],
    "auto_backup": False,
}

_cache: dict = {}


def clear_cache() -> None:
    _cache.clear()


async def get(key: str):
    if key not in _cache:
        doc = await mongo.col(mongo.SETTINGS).find_one({"_id": key})
        _cache[key] = doc["value"] if doc and "value" in doc else copy.deepcopy(DEFAULTS.get(key))
    return copy.deepcopy(_cache[key])


async def set(key: str, value) -> None:  # noqa: A001 - intentional name
    await mongo.col(mongo.SETTINGS).update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)
    _cache[key] = copy.deepcopy(value)


async def toggle(key: str) -> bool:
    new = not bool(await get(key))
    await set(key, new)
    return new


async def update_in(key: str, sub: str, value) -> None:
    cur = await get(key) or {}
    cur[sub] = value
    await set(key, cur)
