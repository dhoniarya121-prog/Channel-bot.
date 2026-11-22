"""Editing posts: shared by new posts (auto) and old posts (runs started from the menu).

Modes: auto (obey the channel's ON/OFF switches) | caption | buttons | both | unbutton
"""
import asyncio
import logging
import os

from utils import jobs, store, tg
from utils.captioning import compute_caption

log = logging.getLogger(__name__)
MEDIA_ATTRS = ("document", "video", "audio", "animation", "voice", "photo")
MODES = {"caption": "📝 Captions", "buttons": "🔘 Buttons", "both": "📝🔘 Captions + Buttons",
         "unbutton": "🚫 Remove buttons"}
BATCH = 100
DELAY = float(os.getenv("EDIT_DELAY", "0.3"))        # pause between old-post edits (was 1.2s)
AUTO_DELAY = float(os.getenv("AUTO_EDIT_DELAY", "0.15"))  # pause after a new-post edit (was 0.6s)
_lock = asyncio.Lock()
_tasks: set = set()


def media_of(m):
    return next((getattr(m, a) for a in MEDIA_ATTRS if getattr(m, a, None)), None)


def keep_markup(m):
    """Existing URL-only keyboard of a post (kept when we only change the caption)."""
    mk = getattr(m, "reply_markup", None)
    rows = getattr(mk, "inline_keyboard", None)
    if rows and all(getattr(b, "url", None) for row in rows for b in row):
        return mk
    return None


async def apply(client, m, mode: str = "auto") -> str:
    """Edit one post. Returns 'edited' or 'skip'. Raises pyrogram errors (MessageNotModified, FloodWait ...)."""
    chat_id = m.chat.id
    eff = store.effective(chat_id)
    media = media_of(m)
    if mode == "unbutton":
        if not getattr(m, "reply_markup", None):
            return "skip"
        await client.edit_message_reply_markup(chat_id, m.id, reply_markup=None)
        return "edited"
    auto = mode == "auto"
    want_caption = mode in ("caption", "both") or (auto and eff["caption"])
    want_btn = bool(eff["buttons"]) and (mode in ("buttons", "both") or (auto and eff["buttons_on"]))
    markup = tg.url_markup(eff["buttons"], eff["per_row"], eff["color"], eff["font"]) if want_btn else None
    if want_caption and media:
        cap = m.caption
        new = compute_caption(cap.html if cap else "", getattr(media, "file_name", None), chat_id)
        await client.edit_message_caption(chat_id, m.id, new, reply_markup=markup or keep_markup(m))
        return "edited"
    if want_btn and (media or getattr(m, "text", None)):
        await client.edit_message_reply_markup(chat_id, m.id, reply_markup=markup)
        return "edited"
    return "skip"


async def auto_edit(client, m) -> None:
    """New channel post: edit it, gently (flood-wait aware)."""
    from pyrogram.errors import ChatAdminRequired, FloodWait, MessageNotModified, RPCError
    async with _lock:
        for _ in range(2):
            try:
                await apply(client, m, "auto")
                break
            except MessageNotModified:
                break
            except FloodWait as e:
                await asyncio.sleep(int(getattr(e, "value", 1)) + 1)
            except ChatAdminRequired:
                log.error("Edit failed in %s: bot needs the 'Edit messages' admin right", m.chat.id)
                break
            except RPCError as e:
                log.error("Edit failed in %s: %s", m.chat.id, type(e).__name__)
                break
        await asyncio.sleep(AUTO_DELAY)


def _stop_markup():
    return tg.menu_markup([[{"text": "⏹ Stop", "data": "stop"}]])


async def start_job(client, chat_id: int, mode: str, lo: int, hi: int, owner_id: int, reply_to):
    """Start an old-posts run. Returns the status message, or None when another job is already running."""
    if not jobs.acquire("old posts", owner_id):
        return None
    try:
        status = await reply_to.reply_text(f"🕘 Started: {MODES.get(mode, mode)} on IDs {lo}–{hi}…",
                                           reply_markup=_stop_markup())
    except Exception:
        jobs.release()
        raise
    task = asyncio.create_task(_job(client, chat_id, mode, lo, hi, owner_id, status))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return status


async def _job(client, chat, mode, start, end, owner_id, status):
    from pyrogram.errors import FloodWait, MessageNotModified, RPCError
    done = unchanged = failed = scanned = 0
    last = start - 1
    try:
        for lo in range(start, end + 1, BATCH):
            if jobs.should_stop():
                break
            ids = list(range(lo, min(lo + BATCH - 1, end) + 1))
            try:
                msgs = await client.get_messages(chat, ids)
            except FloodWait as e:
                await asyncio.sleep(int(getattr(e, "value", 1)) + 1)
                msgs = await client.get_messages(chat, ids)
            except RPCError as e:
                log.error("get_messages failed: %s", type(e).__name__)
                failed += len(ids)
                continue
            for m in msgs:
                if jobs.should_stop():
                    break
                last = m.id if m else last
                if not m or getattr(m, "empty", False):
                    continue
                try:
                    try:
                        res = await apply(client, m, mode)
                    except FloodWait as e:  # wait, then retry this same post once
                        await asyncio.sleep(int(getattr(e, "value", 1)) + 1)
                        res = await apply(client, m, mode)
                    if res == "edited":
                        scanned += 1
                        done += 1
                        await asyncio.sleep(DELAY)
                except MessageNotModified:
                    scanned += 1
                    unchanged += 1
                    await asyncio.sleep(DELAY)
                except FloodWait as e:
                    scanned += 1
                    failed += 1
                    await asyncio.sleep(int(getattr(e, "value", 1)) + 1)
                except RPCError as e:
                    scanned += 1
                    failed += 1
                    log.error("edit %s/%s failed: %s", chat, m.id, type(e).__name__)
                    await asyncio.sleep(DELAY)
            try:
                await status.edit_text(f"🕘 {MODES.get(mode, mode)} — up to ID <b>{ids[-1]}</b> of {end}\n"
                                       f"✅ {done}  ➖ {unchanged}  ❌ {failed}", reply_markup=_stop_markup())
            except Exception:
                pass
    except Exception:
        log.exception("old posts job crashed")
    finally:
        stopped = jobs.should_stop()
        jobs.release()
    try:
        await client.send_message(owner_id, f"{'⏹ Stopped' if stopped else '✅ Finished'} — {MODES.get(mode, mode)}, "
                                            f"IDs {start}–{end}\n\nPosts touched: {scanned}\n✅ Updated: {done}\n"
                                            f"➖ Already up to date: {unchanged}\n❌ Failed: {failed}"
                                  + (f"\n\nContinue from ID <code>{last + 1}</code>." if stopped else ""))
    except Exception:
        pass
