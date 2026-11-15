"""Premium: user status screens + admin premium management."""
import logging

from pyrogram import Client, filters

from database import premium, settings, users
from keyboards.common import btn, kb, pager, pages
from keyboards.user import home_btn
from utils import adminui, router, state, tg
from utils.adminui import back, onoff
from utils.i18n import t
from utils.text import esc, fmt_dt, parse_int, time_left, trunc
from utils.views import dev, quota_text

log = logging.getLogger(__name__)
PER_PAGE = 8


async def premium_text(doc: dict) -> str:
    lang = doc.get("lang", "en")
    st = await premium.status(doc["_id"])
    if st["active"]:
        return t(lang, "prem_active", until=fmt_dt(st["until"]), left=time_left(st["until"]))
    return t(lang, "prem_free", quota=quota_text(doc), dev=dev())


@Client.on_message(filters.command(["premium", "plans"]) & filters.private)
async def premium_cmd(client, message):
    doc = await users.get(message.from_user.id)
    await message.reply_text(await premium_text(doc), reply_markup=home_btn(doc.get("lang", "en")))


@router.cb("u:prem")
async def cb_user_premium(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, await premium_text(doc), home_btn(doc.get("lang", "en")))


# ------------------------------------------------------------------- admin
def duration_kb(uid: int, back_to: str):
    return kb([btn("7 days", f"adm:p:grant:{uid}:7"), btn("30 days", f"adm:p:grant:{uid}:30"),
               btn("90 days", f"adm:p:grant:{uid}:90")],
              [btn("✏️ Custom days", f"adm:p:custom:{uid}")], back(back_to))


@router.cb("adm:p", "premium")
async def adm_premium(client, cq, args):
    n = await premium.count_active()
    notify = await settings.get("premium_notify")
    await tg.show(cq, f"💎 <b>Premium Management</b>\n\nActive premium users: <b>{n}</b>\nExpiry notices: {onoff(notify)}",
                  kb([btn("📋 Premium users", "adm:p:list:0")],
                     [btn("➕ Grant / renew", "adm:p:gi"), btn("➖ Revoke", "adm:p:ri")],
                     [btn(f"🔔 Expiry notices: {onoff(notify)}", "adm:p:notif")],
                     [btn("🧹 Run expiry sweep now", "adm:p:sweep")], back()))


@router.cb("adm:p:list", "premium")
async def adm_premium_list(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    total = await premium.count_active()
    rows = await premium.list_active(page * PER_PAGE, PER_PAGE)
    lines = [f"💎 <b>Premium users</b> ({total}) — page {page + 1}/{pages(total, PER_PAGE)}", ""]
    buttons = []
    for p in rows:
        u = await users.get(p["_id"]) or {}
        lines.append(f"• <code>{p['_id']}</code> {esc(trunc(u.get('first_name', ''), 20))} — {fmt_dt(p['end'])} ({time_left(p['end'])})")
        buttons.append([btn(f"{trunc(u.get('first_name') or p['_id'], 24)}", f"adm:u:view:{p['_id']}")])
    if not rows:
        lines.append("No active premium users.")
    buttons.append(pager("adm:p:list", page, total, PER_PAGE))
    buttons.append(back("adm:p"))
    await tg.show(cq, "\n".join(lines), kb(*buttons))


@router.cb("adm:p:gi", "premium")
async def adm_grant_ask(client, cq, args):
    await adminui.ask(cq, "adm_p_gi", "➕ Send the <b>user ID or @username</b> to grant/renew premium:")


@router.on_input("adm_p_gi", "premium")
async def in_grant_id(client, message, ctx):
    u = await users.find(message.text or "")
    if not u:
        await message.reply_text("❌ User not found (they must have started the bot).")
        return
    await message.reply_text(f"💎 Choose duration for <b>{esc(u.get('first_name'))}</b> (<code>{u['_id']}</code>):",
                             reply_markup=duration_kb(u["_id"], "adm:p"))


@router.cb("adm:p:grant", "premium")
async def adm_grant(client, cq, args):
    uid, days = int(args[0]), int(args[1])
    end = await premium.activate(uid, days, cq.from_user.id)
    if not end:
        return ("User not found.", True)
    doc = await users.get(uid)
    await tg.notify(client, uid, t(doc.get("lang", "en"), "prem_granted", days=days))
    await tg.show(cq, f"✅ Premium active for <code>{uid}</code> until <b>{fmt_dt(end)}</b>.",
                  kb([btn("👤 User card", f"adm:u:view:{uid}")], back("adm:p")))


@router.cb("adm:p:custom", "premium")
async def adm_custom_ask(client, cq, args):
    await adminui.ask(cq, "adm_p_cd", f"✏️ Send the number of days (1–{premium.MAX_DAYS}) for user <code>{args[0]}</code>:",
                      uid=int(args[0]))


@router.on_input("adm_p_cd", "premium")
async def in_custom_days(client, message, ctx):
    days = parse_int(message.text, 1, premium.MAX_DAYS) if message.text else None
    if days is None:
        state.set_state(message.from_user.id, "adm_p_cd", **ctx)
        await message.reply_text(f"⚠️ Send a whole number between 1 and {premium.MAX_DAYS}.")
        return
    end = await premium.activate(ctx["uid"], days, message.from_user.id)
    if not end:
        await message.reply_text("❌ User not found.")
        return
    doc = await users.get(ctx["uid"])
    await tg.notify(client, ctx["uid"], t(doc.get("lang", "en"), "prem_granted", days=days))
    await message.reply_text(f"✅ Premium active for <code>{ctx['uid']}</code> until <b>{fmt_dt(end)}</b>.",
                             reply_markup=kb(back("adm:p")))


@router.cb("adm:p:ri", "premium")
async def adm_revoke_ask(client, cq, args):
    await adminui.ask(cq, "adm_p_ri", "➖ Send the <b>user ID or @username</b> to revoke premium:")


@router.on_input("adm_p_ri", "premium")
async def in_revoke_id(client, message, ctx):
    u = await users.find(message.text or "")
    if not u:
        await message.reply_text("❌ User not found.")
        return
    await premium.revoke(u["_id"])
    await message.reply_text(f"✅ Premium revoked for <code>{u['_id']}</code>.", reply_markup=kb(back("adm:p")))


@router.cb("adm:p:revoke", "premium")
async def adm_revoke(client, cq, args):
    uid = int(args[0])
    await premium.revoke(uid)
    await tg.show(cq, f"✅ Premium revoked for <code>{uid}</code>.",
                  kb([btn("👤 User card", f"adm:u:view:{uid}")], back("adm:p")))


@router.cb("adm:p:notif", "premium")
async def adm_notif(client, cq, args):
    await settings.toggle("premium_notify")
    await adm_premium(client, cq, args)


@router.cb("adm:p:sweep", "premium")
async def adm_sweep(client, cq, args):
    expired = await premium.expire_due()
    for uid in expired:
        doc = await users.get(uid)
        await tg.notify(client, uid, t((doc or {}).get("lang", "en"), "prem_expired", dev=dev()))
    return (f"Expired and downgraded: {len(expired)}", True)
