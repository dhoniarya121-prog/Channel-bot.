"""Sending catalogue files to users (access control enforced here)."""
import logging

from pyrogram.errors import RPCError

from database import files
from utils import tg

log = logging.getLogger(__name__)


async def deliver(client, user_doc: dict, token: str, is_admin: bool = False) -> str:
    """Returns 'ok' or a reason code (no_file | pending | premium_only | banned | unavailable)."""
    f = await files.get(token)
    allowed, why = files.can_access(f, user_doc, is_admin)
    if not allowed:
        return why
    try:
        await tg.safe(client.send_cached_media, user_doc["_id"], f["file_id"],
                      caption=(f.get("caption_html") or f.get("caption") or "")[:1024])
    except RPCError as e:
        log.warning("deliver %s failed: %s", token, type(e).__name__)
        return "unavailable"
    return "ok"


REASON_KEYS = {"no_file": "share_nofile", "pending": "share_pending", "premium_only": "share_noaccess",
               "banned": "share_noperm", "unavailable": "unavailable", "no_user": "share_nofile"}
