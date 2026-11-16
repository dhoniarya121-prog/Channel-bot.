"""Owner command: edit captions of files that are already in the channel.

  /oldposts https://t.me/c/1234567890/900        -> posts 1..900 of that channel
  /oldposts -1001234567890 100 900               -> posts 100..900
  /oldposts @channelname 500                     -> posts 1..500
  /stopold                                       -> stop the running job
"""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified, RPCError

import config
from utils import jobs
from utils.buttons import parse_post_link
from utils.captioning import compute_caption
from utils.oldposts import parse_range

log = logging.getLogger(__name__)
BATCH = 100
DELAY = 1.2
owner = filters.user(list(config.OWNER_IDS)) if config.OWNER_IDS else filters.user([0])
USAGE = ("Use:\n<code>/oldposts https://t.me/c/1234567890/900</code>\n<code>/oldposts -1001234567890 100 900</code>\n"
         "<code>/oldposts @channelname 500</code>")


def parse_args(args: list[str]):
    """Returns (chat, start, end) or None."""
    if not args:
        return None
    ref = parse_post_link(args[0])
    if ref:
        return ref[0], 1, ref[1]
    chat = args[0]
    chat = int(chat) if chat.lstrip("-").isdigit() else chat
    rng = parse_range(" ".join(args[1:]))
    return (chat, *rng) if rng else None


@Client.on_message(filters.command("oldposts") & filters.private & owner)
async def oldposts_cmd(client, message):
    parsed = parse_args(message.command[1:])
    if not parsed:
        await message.reply_text("⚠️ " + USAGE)
        return
    if not jobs.acquire("old posts"):
        await message.reply_text("⚠️ A job is already running. /stopold to stop it.")
        return
    chat, start, end = parsed
    status = await message.reply_text(f"🕘 Started: IDs {start}–{end}… (/stopold to stop)")
    asyncio.create_task(_job(client, chat, start, end, message.from_user.id, status))


@Client.on_message(filters.command("stopold") & filters.private & owner)
async def stop_cmd(client, message):
    jobs.request_stop()
    await message.reply_text("⏹ Stopping after the current post…")


async def _job(client, chat, start, end, owner_id, status):
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
                media = next((getattr(m, a) for a in ("document", "video", "audio", "animation", "voice", "photo")
                              if getattr(m, a, None)), None)
                if not media:
                    continue
                scanned += 1
                cap = m.caption
                new = compute_caption(cap.html if cap else "", getattr(media, "file_name", None))
                try:
                    await client.edit_message_caption(chat, m.id, new)
                    done += 1
                except MessageNotModified:
                    unchanged += 1
                except FloodWait as e:
                    await asyncio.sleep(int(getattr(e, "value", 1)) + 1)
                    failed += 1
                except RPCError as e:
                    failed += 1
                    log.error("edit %s/%s failed: %s", chat, m.id, type(e).__name__)
                await asyncio.sleep(DELAY)
            try:
                await status.edit_text(f"🕘 Working… up to ID <b>{ids[-1]}</b> of {end}\n✅ {done}  ➖ {unchanged}  ❌ {failed}")
            except Exception:
                pass
    except Exception:
        log.exception("old posts job crashed")
    finally:
        stopped = jobs.should_stop()
        jobs.release()
    try:
        await client.send_message(owner_id, f"{'⏹ Stopped' if stopped else '✅ Finished'} — IDs {start}–{end}\n\n"
                                            f"Files found: {scanned}\n✅ Updated: {done}\n➖ Already up to date: {unchanged}\n"
                                            f"❌ Failed: {failed}" + (f"\n\nContinue from ID <code>{last + 1}</code>." if stopped else ""))
    except Exception:
        pass
