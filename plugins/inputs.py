"""Routes private messages: pending admin/user prompts first, then plain-text file search."""
import logging

from pyrogram import Client, StopPropagation, filters

from database import admins, users
from plugins.filters import do_search
from utils import router, state

log = logging.getLogger(__name__)


@Client.on_message(filters.private & ~filters.service & ~filters.regex(r"^/"), group=0)
async def route(client, message):
    if not message.from_user:
        return
    uid = message.from_user.id
    st = state.pop_state(uid)
    if st:
        action, ctx = st
        entry = router.get_input(action)
        if not entry:
            return
        fn, perm = entry
        if perm and not await admins.has_perm(uid, None if perm == "admin" else perm):
            await message.reply_text("🚫 You don't have permission.")
            raise StopPropagation
        try:
            await fn(client, message, ctx)
        except StopPropagation:
            raise
        except Exception:
            log.exception("input handler failed: %s", action)
            await message.reply_text("⚠️ Something went wrong. It was logged.")
        raise StopPropagation
    if message.text:
        await do_search(client, message, message.text)
        raise StopPropagation
