"""Single callback dispatcher: resolves callback_data through utils.router and enforces permissions."""
import logging

from pyrogram import Client, StopPropagation
from pyrogram.errors import MessageNotModified

from database import admins
from utils import router

log = logging.getLogger(__name__)


def _answer_args(res):
    if isinstance(res, tuple):
        return res[0], bool(res[1])
    return res, False


@Client.on_callback_query(group=0)
async def dispatch(client, cq):
    data = cq.data or ""
    hit = router.resolve_cb(data)
    if not hit:
        await cq.answer("This button has expired.", show_alert=True)
        return
    fn, perm, args = hit
    if perm and not await admins.has_perm(cq.from_user.id, None if perm == "admin" else perm):
        await cq.answer("🚫 You don't have permission.", show_alert=True)
        return
    try:
        res = await fn(client, cq, args)
    except StopPropagation:
        raise
    except MessageNotModified:
        res = None
    except Exception:
        log.exception("callback failed: %s", ":".join(data.split(":")[:3]))
        res = ("⚠️ Something went wrong. It was logged.", True)
    text, alert = _answer_args(res)
    try:
        await cq.answer(text, show_alert=alert)
    except Exception:
        pass
