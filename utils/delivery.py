"""Sending catalogue files to users. Receiving a file (a copy the user can save or forward) is what the daily
limit counts; the access rules and the limit are enforced here, in one place."""
import logging

from pyrogram.errors import RPCError

from database import files, settings, sharing
from utils import tg
from utils.i18n import t

log = logging.getLogger(__name__)

REASON_KEYS = {"no_file": "share_nofile", "pending": "share_pending", "premium_only": "share_noaccess",
               "banned": "share_noperm", "unavailable": "unavailable", "no_user": "share_nofile",
               "disabled": "share_disabled", "no_permission": "share_noperm", "no_access": "share_noaccess"}


async def reason_text(lang: str, reason: str, doc: dict | None = None) -> str:
    if reason == "limit":
        if await settings.get("quota_mode") == "daily":
            return t(lang, "share_limit_daily", limit=(doc or {}).get("daily_limit_eff", 0),
                     bonus=await settings.get("referral_reward_quota"))
        return t(lang, "share_limit")
    return t(lang, REASON_KEYS.get(reason, "unavailable"))


async def deliver(client, user_doc: dict, token: str, is_admin: bool = False) -> str:
    """Returns 'ok' or a reason code (no_file | pending | premium_only | banned | limit | disabled | unavailable)."""
    f = await files.get(token)
    allowed, why = files.can_access(f, user_doc, is_admin)
    if not allowed:
        return why
    mode = ""
    if not is_admin:                                   # first copy of a file spends one permission, repeats are free
        res = await sharing.share_file(user_doc["_id"], token)
        if not res.ok:
            return res.reason
        mode = res.mode if res.reason == "ok" else ""
    try:
        await tg.safe(client.send_cached_media, user_doc["_id"], f["file_id"],
                      caption=(f.get("caption_html") or f.get("caption") or "")[:1024],
                      protect_content=bool(await settings.get("protect_content")))
    except RPCError as e:
        log.warning("deliver %s failed: %s", token, type(e).__name__)
        if mode:
            await sharing.undo(user_doc["_id"], token, mode)      # user must not lose a permission for nothing
        return "unavailable"
    return "ok"
