"""Broadcast (admin only): audience selection, confirmation, progress, FloodWait handling."""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, PeerIdInvalid, RPCError, UserIsBlocked

from database import admins, broadcasts, users
from keyboards.common import btn, kb
from utils import adminui, broadcast, router, state, tg
from utils.adminui import back
from utils.text import fmt_dt

log = logging.getLogger(__name__)
_TASKS: set = set()
LABELS = {"all": "👥 All users", "premium": "💎 Premium", "free": "🆓 Free", "verified": "✅ Verified",
          "active7d": "🔥 Active 7 days", "new7d": "🆕 New 7 days"}


def make_sender(client, from_chat: int, message_id: int):
    async def send(uid: int) -> str:
        for _ in range(3):
            try:
                await client.copy_message(uid, from_chat, message_id)
                return "ok"
            except FloodWait as e:                       # wait it out, then retry the same user
                await asyncio.sleep(tg.flood_seconds(e) + 1)
            except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid):
                return "blocked"
            except RPCError as e:
                log.info("broadcast to %s failed: %s", uid, type(e).__name__)
                return "failed"
        return "failed"
    return send


def confirm_view(doc: dict):
    return (f"📢 <b>Broadcast ready</b>\n\nAudience: <b>{LABELS.get(doc['audience'], doc['audience'])}</b>\n"
            f"Recipients: <b>{doc['total']}</b>\n\nThe message you sent will be copied to every recipient.",
            kb([btn("🚀 Start broadcast", f"adm:bc:go:{doc['_id']}"), btn("✖️ Cancel", f"adm:bc:x:{doc['_id']}")]))


@router.cb("adm:bc", "broadcast")
async def adm_broadcast(client, cq, args):
    rows = [[btn(LABELS[a], f"adm:bc:a:{a}")] for a in users.AUDIENCES]
    await tg.show(cq, "📢 <b>Broadcast</b>\n\nChoose who should receive it:",
                  kb(*rows, [btn("📜 History", "adm:bc:hist")], back()))


@router.cb("adm:bc:a", "broadcast")
async def adm_bc_audience(client, cq, args):
    aud = args[0] if args and args[0] in users.AUDIENCES else "all"
    await adminui.ask(cq, "adm_bc_msg", f"📢 Audience: <b>{LABELS[aud]}</b>\n\nNow send the message to broadcast "
                                        "(text, photo, video, document… formatting is kept).", audience=aud)


@router.on_input("adm_bc_msg", "broadcast")
async def in_bc_message(client, message, ctx):
    try:
        doc, _ = await broadcast.launch(message.from_user.id, ctx["audience"], message.chat.id, message.id)
    except PermissionError:
        await message.reply_text("🚫 You don't have the broadcast permission.")
        return
    text, markup = confirm_view(doc)
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_cmd(client, message):
    uid = message.from_user.id
    if not await admins.has_perm(uid, "broadcast"):
        await message.reply_text("🚫 You don't have the broadcast permission.")
        return
    if not message.reply_to_message:
        await message.reply_text("Reply to the message you want to broadcast with <code>/broadcast [all|premium|free|verified|active7d|new7d]</code>")
        return
    aud = message.command[1] if len(message.command) > 1 else "all"
    if aud not in users.AUDIENCES:
        await message.reply_text("Unknown audience. Use: " + ", ".join(users.AUDIENCES))
        return
    doc, _ = await broadcast.launch(uid, aud, message.chat.id, message.reply_to_message.id)
    text, markup = confirm_view(doc)
    await message.reply_text(text, reply_markup=markup)


@router.cb("adm:bc:go", "broadcast")
async def adm_bc_go(client, cq, args):
    doc = await broadcasts.claim_start(args[0])
    if not doc:
        return ("This broadcast was already started or cancelled.", True)
    ids = await users.audience(doc["audience"])
    stop_kb = kb([btn("⏹ Stop", f"adm:bc:stop:{doc['_id']}")])
    await tg.show(cq, f"📢 Broadcasting to <b>{len(ids)}</b> users…", stop_kb)
    send = make_sender(client, doc["from_chat"], doc["message_id"])

    async def on_progress(i, total, sent, failed, blocked):
        try:
            await tg.show(cq, f"📢 Progress: <b>{i}/{total}</b>\n✅ {sent}  🚫 {blocked}  ❌ {failed}", stop_kb)
        except Exception:
            pass

    async def job():
        rep = await broadcast.run(doc["_id"], ids, send, on_progress)
        icon = "✅ Finished" if rep["status"] == "done" else "⏹ Stopped"
        await tg.notify(client, cq.from_user.id,
                        f"{icon}\n\nTotal: {rep['total']}\n✅ Sent: {rep['sent']}\n🚫 Blocked/deactivated: {rep['blocked']}\n❌ Failed: {rep['failed']}",
                        kb(back("adm:bc")))
    task = asyncio.create_task(job())
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


@router.cb("adm:bc:stop", "broadcast")
async def adm_bc_stop(client, cq, args):
    broadcast.cancel(args[0])
    return "Stopping after the current user…"


@router.cb("adm:bc:x", "broadcast")
async def adm_bc_cancel(client, cq, args):
    d = await broadcasts.get(args[0])
    if d and d["status"] == "pending":
        await broadcasts.finish(args[0], "cancelled", 0, 0, 0)
    await adm_broadcast(client, cq, [])
    return "Cancelled."


@router.cb("adm:bc:hist", "broadcast")
async def adm_bc_history(client, cq, args):
    rows = await broadcasts.recent(8)
    lines = ["📜 <b>Recent broadcasts</b>", ""] + [
        f"• {fmt_dt(b['created_at'])} · {LABELS.get(b['audience'], b['audience'])} · {b['status']} · ✅{b['sent']} 🚫{b['blocked']} ❌{b['failed']} / {b['total']}"
        for b in rows] if rows else ["📜 <b>Recent broadcasts</b>", "", "None yet."]
    await tg.show(cq, "\n".join(lines), kb(back("adm:bc")))
