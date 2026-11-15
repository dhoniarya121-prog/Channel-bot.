"""Admin: add caption links (and buttons) to files that were already posted in a channel."""
import asyncio
import logging

from pyrogram.errors import MessageNotModified, RPCError

from database import channels, files, settings
from keyboards.channel import channel_markup
from keyboards.common import btn, kb
from utils import adminui, jobs, router, state, tg
from utils.adminui import back
from utils.captioning import compute_caption
from utils.oldposts import parse_range
from utils.text import trunc

log = logging.getLogger(__name__)
BATCH = 100
DELAY = 1.2          # seconds between edits: keeps well under Telegram's edit flood limits


@router.cb("adm:ch:old", "channels")
async def adm_old_menu(client, cq, args):
    chs = await channels.list_role("source")
    if not chs:
        return ("Add a caption channel first.", True)
    await tg.show(cq, "🕘 <b>Update old posts</b>\n\nChoose the channel. The bot will fetch old posts by message ID, "
                      "add the caption links (current template) and the channel buttons, and index the files for search.",
                  kb(*[[btn(trunc(c["title"], 30), f"adm:ch:oc:{c['chat_id']}")] for c in chs], back("adm:ch")))


@router.cb("adm:ch:oc", "channels")
async def adm_old_pick(client, cq, args):
    await adminui.ask(cq, "adm_ch_old",
                      "Send the range of message IDs to process:\n"
                      "• the <b>link of the newest post</b> (processes from the first post up to it), or\n"
                      "• <code>from to</code> e.g. <code>100 900</code>, or one number = 1 to that ID.\n\n"
                      f"Speed ≈ 1 post per {DELAY:.1f}s (5000 posts ≈ 100 min). Only posts with a file are changed.",
                      chat_id=int(args[0]))


@router.on_input("adm_ch_old", "channels")
async def in_old_range(client, message, ctx):
    rng = parse_range(message.text or "")
    if not rng:
        state.set_state(message.from_user.id, "adm_ch_old", **ctx)
        await message.reply_text("⚠️ Send a post link, a number, or <code>from to</code> (or /cancel).")
        return
    if not await settings.get("auto_caption"):
        await message.reply_text("⚠️ Automatic caption editing is OFF (Caption Settings). Turn it ON first.")
        return
    if not jobs.acquire("update old posts"):
        await message.reply_text(f"⚠️ Another job is running: {jobs.busy()}")
        return
    status = await message.reply_text(f"🕘 Started: IDs {rng[0]}–{rng[1]}…", reply_markup=kb([btn("⏹ Stop", "adm:ch:stop")]))
    asyncio.create_task(_job(client, ctx["chat_id"], rng[0], rng[1], message.from_user.id, status))


@router.cb("adm:ch:stop", "channels")
async def adm_old_stop(client, cq, args):
    jobs.request_stop()
    return "Stopping after the current post…"


async def _job(client, chat_id: int, start: int, end: int, admin_id: int, status):
    done = unchanged = failed = scanned = 0
    last = start - 1
    try:
        markup = await channel_markup()
        for lo in range(start, end + 1, BATCH):
            if jobs.should_stop():
                break
            ids = list(range(lo, min(lo + BATCH - 1, end) + 1))
            try:
                msgs = await tg.safe(client.get_messages, chat_id, ids)
            except RPCError as e:
                log.error("old posts: get_messages failed in %s: %s", chat_id, type(e).__name__)
                failed += len(ids)
                continue
            for m in msgs:
                if jobs.should_stop():
                    break
                last = m.id if m else last
                if not m or getattr(m, "empty", False):
                    continue
                media = tg.extract_media(m)
                if not media:
                    continue
                scanned += 1
                original_html = media.pop("caption_html")
                f, _ = await files.add_channel_file(chat_id, m.id, media)
                new_caption = await compute_caption(original_html, media.get("file_name"))
                try:
                    await tg.safe(client.edit_message_caption, chat_id, m.id, new_caption, reply_markup=markup)
                    await files.set_caption(f["_id"], new_caption)
                    done += 1
                except MessageNotModified:
                    unchanged += 1
                except RPCError as e:
                    failed += 1
                    log.error("old posts: edit %s/%s failed: %s", chat_id, m.id, type(e).__name__)
                await asyncio.sleep(DELAY)
            try:
                await status.edit_text(f"🕘 Working… up to ID <b>{ids[-1]}</b> of {end}\n✅ {done}  ➖ {unchanged}  ❌ {failed}",
                                       reply_markup=kb([btn("⏹ Stop", "adm:ch:stop")]))
            except Exception:
                pass
    except Exception:
        log.exception("old posts job crashed")
    finally:
        stopped = jobs.should_stop()
        jobs.release()
    await tg.notify(client, admin_id,
                    f"{'⏹ Stopped' if stopped else '✅ Finished'} — IDs {start}–{end}\n\nFiles found: {scanned}\n✅ Updated: {done}\n"
                    f"➖ Already up to date: {unchanged}\n❌ Failed: {failed}"
                    + (f"\n\nContinue later from ID <code>{last + 1}</code>." if stopped else ""),
                    kb(back("adm:ch")))
