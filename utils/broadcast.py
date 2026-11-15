"""Broadcast engine. Telegram specifics (FloodWait etc.) live in the injected `send` coroutine."""
import asyncio
import logging
from typing import Awaitable, Callable

from database import admins, broadcasts, users

log = logging.getLogger(__name__)
Send = Callable[[int], Awaitable[str]]        # returns "ok" | "blocked" | "failed"
_CANCEL: set[str] = set()


async def launch(admin_id: int, audience: str, from_chat: int, message_id: int) -> tuple[dict, list[int]]:
    """Admin-only: authorises, resolves the audience and stores the broadcast record."""
    if not await admins.has_perm(admin_id, "broadcast"):
        raise PermissionError("broadcast permission required")
    ids = await users.audience(audience)
    doc = await broadcasts.create(admin_id, audience, from_chat, message_id, len(ids))
    return doc, ids


def cancel(bid: str) -> None:
    _CANCEL.add(bid)


async def run(bid: str, ids: list[int], send: Send, on_progress=None, delay: float = 0.04,
              progress_every: int = 25) -> dict:
    sent = failed = blocked = 0
    status = "done"
    for i, uid in enumerate(ids, 1):
        if bid in _CANCEL:
            status = "cancelled"
            break
        try:
            res = await send(uid)
        except Exception as e:                                  # never let one user stop the run
            log.warning("broadcast send error: %s", type(e).__name__)
            res = "failed"
        if res == "ok":
            sent += 1
        elif res == "blocked":
            blocked += 1
            await users.mark_blocked(uid)
        else:
            failed += 1
        if i % progress_every == 0:
            await broadcasts.progress(bid, sent, failed, blocked)
            if on_progress:
                await on_progress(i, len(ids), sent, failed, blocked)
        if delay:
            await asyncio.sleep(delay)
    _CANCEL.discard(bid)
    await broadcasts.finish(bid, status, sent, failed, blocked)
    return {"status": status, "sent": sent, "failed": failed, "blocked": blocked, "total": len(ids)}
