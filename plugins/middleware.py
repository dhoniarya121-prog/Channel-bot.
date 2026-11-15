"""Runs before every other handler (group -10): registration, ban, maintenance, rate limit, duplicate taps."""
import logging
import time

from pyrogram import Client, StopPropagation, filters

from database import admins, settings, users
from utils import guards, health, state
from utils.captions import strip_tags
from utils.i18n import t
from utils.ratelimit import limiter
from utils.text import esc

log = logging.getLogger(__name__)
_TAPS: dict = {}


async def screen(tg_user):
    """-> (user_doc, deny_text | None, lang). deny_text '' means: drop silently."""
    uid = tg_user.id
    admin = await admins.is_admin(uid)
    doc, created = await users.register(uid, tg_user.first_name or "", tg_user.username, tg_user.language_code)
    if created:
        state.mark_new(uid)
    lang = doc.get("lang", "en")
    if admin:
        return doc, None, lang
    if doc.get("banned"):
        return doc, t(lang, "banned", reason=esc(doc.get("ban_reason") or "-")), lang
    if await settings.get("maintenance"):
        return doc, (await settings.get("maintenance_msg")) or t(lang, "maintenance"), lang
    if await settings.get("antispam"):
        left = limiter.muted_for(uid)
        if left:
            return doc, (t(lang, "muted", sec=int(left) + 1) if limiter.notify_due(("m", uid), 30) else ""), lang
        window = await settings.get("rate_limit_window")
        ok, retry = limiter.hit(uid, await settings.get("rate_limit_count"), window)
        if not ok:
            mute = await settings.get("spam_mute_seconds")
            if limiter.strike(uid, 3, mute):
                return doc, t(lang, "muted", sec=int(mute)), lang
            return doc, (t(lang, "rate", sec=int(retry) + 1) if limiter.notify_due(("n", uid), window) else ""), lang
    return doc, None, lang


@Client.on_message(filters.private & ~filters.service, group=-10)
async def pre_message(client, message):
    if not message.from_user or message.from_user.is_bot:
        return
    health.mark_update()
    doc, deny, lang = await screen(message.from_user)
    if deny is not None:
        if deny:
            await message.reply_text(deny)
        raise StopPropagation
    payload = ""                                    # force-subscribe gate for EVERYTHING a user does
    if message.text and message.text.startswith("/start"):
        parts = message.text.split(maxsplit=1)
        payload = parts[1][:40] if len(parts) > 1 else ""
    if not await guards.fsub_gate(client, message, message.from_user, payload, lang):
        raise StopPropagation


@Client.on_callback_query(group=-10)
async def pre_callback(client, cq):
    now = time.monotonic()
    key = (cq.from_user.id, cq.message.id if cq.message else 0, cq.data)
    if _TAPS.get(key, 0) > now:                      # duplicate tap / double click within 1.2 s
        await cq.answer()
        raise StopPropagation
    if len(_TAPS) > 2000:
        for k in [k for k, v in _TAPS.items() if v < now]:
            _TAPS.pop(k, None)
    _TAPS[key] = now + 1.2
    health.mark_update()
    doc, deny, lang = await screen(cq.from_user)
    if deny is not None:
        await cq.answer(strip_tags(deny)[:190] if deny else None, show_alert=bool(deny))
        raise StopPropagation
    if not (cq.data or "").startswith("fs:r") and not await guards.fsub_gate(client, cq, cq.from_user, "", lang):
        await cq.answer()
        raise StopPropagation
