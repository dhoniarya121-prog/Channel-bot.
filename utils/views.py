"""Small text helpers shared by plugins."""
import config
from database import users
from utils.i18n import t
from utils.text import esc, fmt_dt, time_left


def quota_text(doc: dict) -> str:
    return "♾️" if users.is_unlimited(doc) else doc.get("quota_display") or str(doc.get("quota_remaining", 0))


def plan_text(doc: dict) -> str:
    if users.is_premium(doc):
        return "Premium 💎"
    return "Unlimited ♾️" if doc.get("unlimited") else "Free"


def profile_text(doc: dict) -> str:
    lang = doc.get("lang", "en")
    until = f"\nPremium until: {fmt_dt(doc.get('premium_until'))} ({time_left(doc.get('premium_until'))})" \
        if users.is_premium(doc) else ""
    return t(lang, "profile", id=doc["_id"], name=esc(doc.get("first_name")), plan=plan_text(doc), until=until,
             quota=quota_text(doc), shared=doc.get("shared_total", 0), verified="✅" if doc.get("verified") else "❌",
             warns=doc.get("warns", 0), refs=doc.get("referral_count", 0), joined=fmt_dt(doc.get("joined_at")))


def dev() -> str:
    return config.DEVELOPER
