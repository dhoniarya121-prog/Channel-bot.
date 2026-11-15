"""File requests + feedback (user side) and their admin review screens."""
import logging

from pyrogram import Client, filters

from database import admins, requests, settings, users
from keyboards.common import btn, kb, pager, pages
from keyboards.user import home_btn
from utils import adminui, router, state, tg
from utils.adminui import back, onoff
from utils.i18n import t
from utils.text import esc, fmt_dt, trunc

log = logging.getLogger(__name__)


async def _check(doc, key_on, perm, lang):
    if not await settings.get(key_on):
        return t(lang, "req_off" if perm == "request" else "fb_off")
    if not users.has_perm(doc, perm):
        return t(lang, "req_noperm" if perm == "request" else "fb_noperm")
    return None


async def create_request(client, message, doc, text: str):
    lang = doc.get("lang", "en")
    text = text.strip()
    if not text:
        await message.reply_text(t(lang, "invalid"))
        return
    auto = await settings.get("auto_approve_requests")
    req, why = await requests.create(doc["_id"], text, auto)
    if not req:
        await message.reply_text(t(lang, "req_limit", n=requests.MAX_PENDING_PER_USER))
        return
    await message.reply_text(t(lang, "req_ok", id=req["_id"]))
    if not auto:
        card = (f"📨 <b>New request</b> <code>{req['_id']}</code>\nFrom: {esc(doc.get('first_name'))} "
                f"(<code>{doc['_id']}</code>)\n\n{esc(req['text'])}")
        markup = kb([btn("✅ Approve", f"adm:q:ok:{req['_id']}"), btn("❌ Reject", f"adm:q:no:{req['_id']}")])
        for aid in await admins.all_ids():
            if await admins.has_perm(aid, "files"):
                await tg.notify(client, aid, card, markup)


@Client.on_message(filters.command("request") & filters.private)
async def request_cmd(client, message):
    doc = await users.get(message.from_user.id)
    lang = doc.get("lang", "en")
    if err := await _check(doc, "requests_enabled", "request", lang):
        await message.reply_text(err)
        return
    text = message.text.split(None, 1)[1] if len(message.command) > 1 else ""
    if text:
        await create_request(client, message, doc, text)
    else:
        state.set_state(doc["_id"], "req_text")
        await message.reply_text(t(lang, "req_prompt"))


@router.cb("u:request")
async def cb_request(client, cq, args):
    doc = await users.get(cq.from_user.id)
    lang = doc.get("lang", "en")
    if err := await _check(doc, "requests_enabled", "request", lang):
        return (err.replace("<b>", "").replace("</b>", ""), True)
    state.set_state(doc["_id"], "req_text")
    await tg.show(cq, t(lang, "req_prompt"), home_btn(lang))


@router.on_input("req_text")
async def in_request(client, message, ctx):
    doc = await users.get(message.from_user.id)
    await create_request(client, message, doc, message.text or "")


@Client.on_message(filters.command("feedback") & filters.private)
async def feedback_cmd(client, message):
    doc = await users.get(message.from_user.id)
    lang = doc.get("lang", "en")
    if err := await _check(doc, "feedback_enabled", "feedback", lang):
        await message.reply_text(err)
        return
    text = message.text.split(None, 1)[1] if len(message.command) > 1 else ""
    if text:
        await requests.add_feedback(doc["_id"], text)
        await message.reply_text(t(lang, "fb_ok"))
    else:
        state.set_state(doc["_id"], "fb_text")
        await message.reply_text(t(lang, "fb_prompt"))


@router.cb("u:fb")
async def cb_feedback(client, cq, args):
    doc = await users.get(cq.from_user.id)
    lang = doc.get("lang", "en")
    if err := await _check(doc, "feedback_enabled", "feedback", lang):
        return (err.replace("<b>", "").replace("</b>", ""), True)
    state.set_state(doc["_id"], "fb_text")
    await tg.show(cq, t(lang, "fb_prompt"), home_btn(lang))


@router.on_input("fb_text")
async def in_feedback(client, message, ctx):
    doc = await users.get(message.from_user.id)
    if not message.text:
        await message.reply_text(t(doc.get("lang", "en"), "invalid"))
        return
    await requests.add_feedback(doc["_id"], message.text)
    await message.reply_text(t(doc.get("lang", "en"), "fb_ok"))


# ------------------------------------------------------------------- admin
@router.cb("adm:q", "files")
async def adm_requests(client, cq, args):
    s = {k: await settings.get(k) for k in ("requests_enabled", "auto_approve_requests", "feedback_enabled")}
    pend = await requests.count("pending")
    _, fb_total = await requests.list_feedback(0, 1)
    await tg.show(cq, f"📨 <b>Requests & Feedback</b>\n\nPending requests: <b>{pend}</b>\nFeedback messages: <b>{fb_total}</b>",
                  kb([btn(f"📨 Review requests ({pend})", "adm:q:pend:0")],
                     [btn(f"💬 Feedback ({fb_total})", "adm:q:fb:0")],
                     [btn(f"Requests: {onoff(s['requests_enabled'])}", "adm:q:tog:requests_enabled")],
                     [btn(f"Auto-approve: {onoff(s['auto_approve_requests'])}", "adm:q:tog:auto_approve_requests")],
                     [btn(f"Feedback: {onoff(s['feedback_enabled'])}", "adm:q:tog:feedback_enabled")],
                     back("adm:f")))


@router.cb("adm:q:tog", "files")
async def adm_req_toggle(client, cq, args):
    if args and args[0] in ("requests_enabled", "auto_approve_requests", "feedback_enabled"):
        await settings.toggle(args[0])
    await adm_requests(client, cq, [])


@router.cb("adm:q:pend", "files")
async def adm_req_pending(client, cq, args):
    idx = int(args[0]) if args and args[0].isdigit() else 0
    rows = await requests.list_status("pending", idx, 1)
    if not rows and idx:
        rows = await requests.list_status("pending", 0, 1)
        idx = 0
    if not rows:
        await tg.show(cq, "✅ No pending requests.", kb(back("adm:q")))
        return
    r = rows[0]
    u = await users.get(r["user_id"]) or {}
    await tg.show(cq, f"📨 <b>Request</b> <code>{r['_id']}</code>\nFrom: {esc(u.get('first_name'))} (<code>{r['user_id']}</code>)\n"
                      f"Date: {fmt_dt(r['created_at'])}\n\n{esc(r['text'])}",
                  kb([btn("✅ Approve", f"adm:q:ok:{r['_id']}"), btn("❌ Reject", f"adm:q:no:{r['_id']}")],
                     [btn("⏭ Skip", f"adm:q:pend:{idx + 1}")], back("adm:q")))


async def _decide(client, cq, rid, status):
    r = await requests.decide(rid, status, cq.from_user.id)
    if not r:
        return ("Already handled.", True)
    u = await users.get(r["user_id"]) or {}
    key = "req_approved" if status == "approved" else "req_rejected"
    await tg.notify(client, r["user_id"], t(u.get("lang", "en"), key, text=esc(trunc(r["text"], 100))))
    await adm_req_pending(client, cq, ["0"])
    return f"Request {status}."


@router.cb("adm:q:ok", "files")
async def adm_req_ok(client, cq, args):
    return await _decide(client, cq, args[0], "approved")


@router.cb("adm:q:no", "files")
async def adm_req_no(client, cq, args):
    return await _decide(client, cq, args[0], "rejected")


@router.cb("adm:q:fb", "files")
async def adm_feedback(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    rows, total = await requests.list_feedback(page * 5, 5)
    lines = [f"💬 <b>Feedback</b> ({total}) — page {page + 1}/{pages(total, 5)}", ""]
    for f in rows:
        u = await users.get(f["user_id"]) or {}
        lines.append(f"<b>{esc(trunc(u.get('first_name', ''), 20))}</b> (<code>{f['user_id']}</code>) · {fmt_dt(f['created_at'])}\n{esc(trunc(f['text'], 300))}\n")
    if not rows:
        lines.append("No feedback yet.")
    await tg.show(cq, "\n".join(lines), kb(pager("adm:q:fb", page, total, 5), back("adm:q")))
