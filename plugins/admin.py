"""Admin panel core: main menu, dashboard, user management, file management, sharing management."""
import logging

from pyrogram import Client, filters

from database import admins, files, premium, requests, settings, sharing, users, logs
from keyboards.common import btn, kb, pager, pages
from utils import adminui, health, router, state, tg
from utils.adminui import back, onoff
from utils.i18n import t
from utils.text import esc, fmt_dt, time_left, trunc, utcnow
from utils.views import plan_text, quota_text

log = logging.getLogger(__name__)
PER = 8


def main_menu_kb():
    return kb([btn("📊 Dashboard", "adm:dash"), btn("👥 User Management", "adm:u")],
              [btn("📁 File Management", "adm:f"), btn("🔗 Sharing Management", "adm:s")],
              [btn("💎 Premium Management", "adm:p"), btn("🎁 Referral Management", "adm:rf")],
              [btn("✏️ Caption Settings", "adm:c"), btn("📡 Channel Settings", "adm:ch")],
              [btn("🔒 Force Subscribe", "adm:fs"), btn("📢 Broadcast", "adm:bc")],
              [btn("📈 Statistics", "adm:st"), btn("👮 Admin Permissions", "adm:ad")],
              [btn("🛡 Security Settings", "adm:sec"), btn("🛠 Maintenance Mode", "adm:mt")],
              [btn("💾 Database Backup", "adm:bk"), btn("🐞 Bot Logs", "adm:lg")],
              [btn("🔄 Restart / Status", "adm:sys")],
              [btn("🏠 User menu", "u:home")])


MAIN_TEXT = "🛠 <b>ROAROIC Admin Panel</b>\n\nChoose a section:"


@Client.on_message(filters.command("admin") & filters.private)
async def admin_cmd(client, message):
    if not await admins.is_admin(message.from_user.id):
        return
    await message.reply_text(MAIN_TEXT, reply_markup=main_menu_kb())


@router.cb("adm:main", "admin")
async def adm_main(client, cq, args):
    state.clear_state(cq.from_user.id)
    await tg.show(cq, MAIN_TEXT, main_menu_kb())


@router.cb("adm:x", "admin")
async def adm_cancel(client, cq, args):
    state.clear_state(cq.from_user.id)
    await tg.show(cq, MAIN_TEXT, main_menu_kb())
    return "Cancelled."


# ------------------------------------------------------------------ dashboard
@router.cb("adm:dash", "stats")
async def adm_dashboard(client, cq, args):
    s = await users.stats()
    snap = await health.snapshot()
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    await tg.show(cq, "📊 <b>Dashboard</b>\n\n"
                      f"👥 Users: <b>{s['total']}</b> (new 24h: {s['new_24h']})\n💎 Premium: <b>{s['premium']}</b>\n"
                      f"🚫 Banned: {s['banned']}\n📁 Files: <b>{await files.count('approved')}</b> approved · "
                      f"<b>{await files.count('pending')}</b> pending\n📨 Pending requests: <b>{await requests.count('pending')}</b>\n"
                      f"🔗 Shares today: <b>{await sharing.count(None, since)}</b>\n\n"
                      f"⏱ Uptime: {snap['uptime']}\n🗄 DB: {'✅ ' + str(snap['db_ms']) + ' ms' if snap['db_ok'] else '❌ down'}",
                  kb([btn("🔄 Refresh", "adm:dash")], back()))


# ------------------------------------------------------------------ users
@router.cb("adm:u", "users")
async def adm_users(client, cq, args):
    await tg.show(cq, "👥 <b>User Management</b>", kb(
        [btn("🔎 Find user", "adm:u:find")], [btn("👥 Recent users", "adm:u:list:0")],
        [btn("🚫 Banned users", "adm:u:banned:0")], back()))


@router.cb("adm:u:find", "users")
async def adm_find(client, cq, args):
    await adminui.ask(cq, "adm_u_find", "🔎 Send a <b>user ID or @username</b>:")


def user_card(u: dict):
    perms = u.get("perms", {})
    flag = lambda p: "✅" if perms.get(p, True) is not False else "❌"
    uid = u["_id"]
    text = (f"👤 <b>{esc(u.get('first_name'))}</b> {('@' + esc(u['username'])) if u.get('username') else ''}\n"
            f"ID: <code>{uid}</code>\nPlan: <b>{plan_text(u)}</b>"
            f"{' · until ' + fmt_dt(u.get('premium_until')) if users.is_premium(u) else ''}\n"
            f"Shares left: <b>{quota_text(u)}</b> · shared: {u.get('shared_total', 0)}\n"
            f"Verified: {'✅' if u.get('verified') else '❌'} · Warns: {u.get('warns', 0)} · "
            f"Banned: {'🚫 ' + esc(u.get('ban_reason') or '') if u.get('banned') else 'no'}\n"
            f"Referrals: {u.get('referral_count', 0)} · Lang: {u.get('lang', 'en')}\n"
            f"Joined: {fmt_dt(u.get('joined_at'))}\nLast active: {fmt_dt(u.get('last_active'))}")
    ban = btn("✅ Unban", f"adm:u:unban:{uid}") if u.get("banned") else btn("🚫 Ban", f"adm:u:ban:{uid}")
    ver = btn("❌ Unverify", f"adm:u:ver:{uid}:0") if u.get("verified") else btn("✅ Verify", f"adm:u:ver:{uid}:1")
    unl = btn("♾ Unlimited: OFF→ON" if not u.get("unlimited") else "♾ Unlimited: ON→OFF", f"adm:u:unl:{uid}:{0 if u.get('unlimited') else 1}")
    return text, kb(
        [ban, btn("⚠️ Warn", f"adm:u:warn:{uid}"), btn("🧹 Clear warns", f"adm:u:cw:{uid}")],
        [ver, unl],
        [btn("♻️ Reset quota", f"adm:u:rq:{uid}"), btn("✏️ Set quota", f"adm:u:sq:{uid}")],
        [btn("💎 Grant premium", f"adm:u:prem:{uid}"), btn("🆓 Set Free plan", f"adm:p:revoke:{uid}")],
        [btn(f"Share {flag('share')}", f"adm:u:perm:{uid}:share"), btn(f"Submit {flag('submit')}", f"adm:u:perm:{uid}:submit")],
        [btn(f"Request {flag('request')}", f"adm:u:perm:{uid}:request"), btn(f"Feedback {flag('feedback')}", f"adm:u:perm:{uid}:feedback")],
        [btn("📜 Activity", f"adm:u:act:{uid}:0"), btn("🔗 Share history", f"adm:u:hist:{uid}")],
        back("adm:u"))


async def show_card(target, uid: int):
    u = await users.get(uid)
    if not u:
        await tg.show(target, "❌ User not found.", kb(back("adm:u")))
        return
    text, markup = user_card(u)
    await tg.show(target, text, markup)


@router.on_input("adm_u_find", "users")
async def in_find(client, message, ctx):
    u = await users.find(message.text or "")
    if not u:
        await message.reply_text("❌ User not found (they must have started the bot).", reply_markup=kb(back("adm:u")))
        return
    text, markup = user_card(u)
    await message.reply_text(text, reply_markup=markup)


@router.cb("adm:u:view", "users")
async def adm_view(client, cq, args):
    await show_card(cq, int(args[0]))


@router.cb("adm:u:list", "users")
async def adm_user_list(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    total = await users.count()
    rows = await users.list_users(page * PER, PER)
    await tg.show(cq, f"👥 <b>Recent users</b> — page {page + 1}/{pages(total, PER)} ({total})",
                  kb(*[[btn(f"{trunc(u.get('first_name') or u['_id'], 22)} · {u['_id']}", f"adm:u:view:{u['_id']}")] for u in rows],
                     pager("adm:u:list", page, total, PER), back("adm:u")))


@router.cb("adm:u:banned", "users")
async def adm_banned_list(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    total = await users.count({"banned": True})
    rows = await users.list_users(page * PER, PER, {"banned": True})
    await tg.show(cq, f"🚫 <b>Banned users</b> — {total}",
                  kb(*[[btn(f"{trunc(u.get('first_name') or u['_id'], 22)} · {u['_id']}", f"adm:u:view:{u['_id']}")] for u in rows],
                     pager("adm:u:banned", page, total, PER), back("adm:u")))


async def _protected(uid: int, actor: int) -> str | None:
    if uid == actor:
        return "You can't do that to yourself."
    if await admins.is_admin(uid):
        return "Admins and owners can't be banned or warned."
    return None


@router.cb("adm:u:ban", "users")
async def adm_ban(client, cq, args):
    uid = int(args[0])
    if err := await _protected(uid, cq.from_user.id):
        return (err, True)
    await users.ban(uid, "Banned by admin", cq.from_user.id)
    await logs.activity(cq.from_user.id, "ban", str(uid))
    await show_card(cq, uid)
    return "User banned."


@router.cb("adm:u:unban", "users")
async def adm_unban(client, cq, args):
    await users.unban(int(args[0]))
    await show_card(cq, int(args[0]))
    return "User unbanned."


@router.cb("adm:u:warn", "users")
async def adm_warn(client, cq, args):
    uid = int(args[0])
    if err := await _protected(uid, cq.from_user.id):
        return (err, True)
    res = await users.warn(uid, cq.from_user.id, "Warned by admin", await settings.get("max_warns"))
    await show_card(cq, uid)
    if res:
        return f"Warning {res[0]} issued" + (" – user auto-banned." if res[1] else ".")


@router.cb("adm:u:cw", "users")
async def adm_clear_warns(client, cq, args):
    await users.clear_warns(int(args[0]))
    await show_card(cq, int(args[0]))
    return "Warnings cleared."


@router.cb("adm:u:ver", "users")
async def adm_verify(client, cq, args):
    await users.set_verified(int(args[0]), args[1] == "1")
    await show_card(cq, int(args[0]))
    return "Updated."


@router.cb("adm:u:unl", "users")
async def adm_unlimited(client, cq, args):
    await users.set_unlimited(int(args[0]), args[1] == "1")
    await show_card(cq, int(args[0]))
    return "Unlimited sharing " + ("granted." if args[1] == "1" else "removed.")


@router.cb("adm:u:rq", "users")
async def adm_reset_quota(client, cq, args):
    n = await users.reset_quota(int(args[0]))
    await show_card(cq, int(args[0]))
    return f"Quota reset to {n}."


@router.cb("adm:u:sq", "users")
async def adm_set_quota_ask(client, cq, args):
    await adminui.ask(cq, "adm_u_sq", f"✏️ Send the new share limit (0–100000) for <code>{args[0]}</code>:", uid=int(args[0]))


@router.on_input("adm_u_sq", "users")
async def in_set_quota(client, message, ctx):
    from utils.text import parse_int
    n = parse_int(message.text, 0, 100000) if message.text else None
    if n is None:
        state.set_state(message.from_user.id, "adm_u_sq", **ctx)
        await message.reply_text("⚠️ Send a whole number between 0 and 100000.")
        return
    await users.set_quota(ctx["uid"], n)
    await message.reply_text(f"✅ Share limit for <code>{ctx['uid']}</code> set to <b>{n}</b>.",
                             reply_markup=kb([btn("👤 User card", f"adm:u:view:{ctx['uid']}")]))


@router.cb("adm:u:prem", "premium")
async def adm_user_premium(client, cq, args):
    from plugins.premium import duration_kb
    await tg.show(cq, f"💎 Grant premium to <code>{args[0]}</code>:", duration_kb(int(args[0]), f"adm:u:view:{args[0]}"))


@router.cb("adm:u:perm", "users")
async def adm_toggle_user_perm(client, cq, args):
    uid, perm = int(args[0]), args[1]
    if perm not in users.DEFAULT_PERMS:
        return ("Unknown permission.", True)
    u = await users.get(uid)
    await users.set_permission(uid, perm, not users.has_perm(u, perm))
    await show_card(cq, uid)


@router.cb("adm:u:act", "users")
async def adm_activity(client, cq, args):
    uid, page = int(args[0]), int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
    rows, total = await logs.user_activity(uid, page * 10, 10)
    lines = [f"📜 <b>Activity</b> of <code>{uid}</code> ({total})", ""] + [
        f"{fmt_dt(r['ts'])} · {esc(r['action'])} {esc(r.get('detail', ''))}" for r in rows] if rows else ["📜 No recorded activity."]
    await tg.show(cq, "\n".join(lines), kb(pager(f"adm:u:act:{uid}", page, total, 10), back(f"adm:u:view:{uid}")))


@router.cb("adm:u:hist", "users")
async def adm_user_history(client, cq, args):
    uid = int(args[0])
    rows = await sharing.history(uid, 0, 10)
    lines = [f"🔗 <b>Share history</b> of <code>{uid}</code>", ""] + [
        f"{fmt_dt(r['ts'])} · {esc(trunc(r.get('file_name') or r['file_token'], 40))}" for r in rows] if rows else ["No shares yet."]
    await tg.show(cq, "\n".join(lines), kb(back(f"adm:u:view:{uid}")))


@Client.on_message(filters.command("ban") & filters.private)
async def ban_cmd(client, message):
    if not await admins.has_perm(message.from_user.id, "users"):
        return
    if len(message.command) < 2 or not message.command[1].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/ban user_id [reason]</code>")
        return
    uid = int(message.command[1])
    if err := await _protected(uid, message.from_user.id):
        await message.reply_text(err)
        return
    ok = await users.ban(uid, " ".join(message.command[2:])[:200] or "Banned by admin", message.from_user.id)
    await message.reply_text("🚫 Banned." if ok else "❌ User not found.")


@Client.on_message(filters.command("unban") & filters.private)
async def unban_cmd(client, message):
    if not await admins.has_perm(message.from_user.id, "users"):
        return
    if len(message.command) < 2 or not message.command[1].lstrip("-").isdigit():
        await message.reply_text("Usage: <code>/unban user_id</code>")
        return
    ok = await users.unban(int(message.command[1]))
    await message.reply_text("✅ Unbanned." if ok else "❌ User not found.")


# ------------------------------------------------------------------ files
@router.cb("adm:f", "files")
async def adm_files(client, cq, args):
    pend = await files.count("pending")
    auto = await settings.get("auto_approve_files")
    await tg.show(cq, f"📁 <b>File Management</b>\n\nApproved: <b>{await files.count('approved')}</b> · Pending: <b>{pend}</b> · "
                      f"Rejected: {await files.count('rejected')}",
                  kb([btn(f"⏳ Pending approvals ({pend})", "adm:f:pend:0")], [btn("📁 Recent files", "adm:f:list:0")],
                     [btn("🗑 Delete by token", "adm:f:del"), btn("📨 Requests & feedback", "adm:q")],
                     [btn(f"Auto-approve submissions: {onoff(auto)}", "adm:f:auto")], back()))


@router.cb("adm:f:auto", "files")
async def adm_auto_approve(client, cq, args):
    await settings.toggle("auto_approve_files")
    await adm_files(client, cq, args)


def file_card(f: dict) -> str:
    return (f"📄 <b>{esc(trunc(f.get('file_name') or f.get('caption') or f['file_type'], 80))}</b>\nToken: <code>{f['_id']}</code>\n"
            f"Type: {f['file_type']} · Size: {f.get('file_size') or '-'}\nSource: {f['source']} · Owner: <code>{f.get('owner_id', '-')}</code>\n"
            f"Status: <b>{f['status']}</b> · Visibility: <b>{f.get('visibility')}</b>\nAdded: {fmt_dt(f['created_at'])}")


@router.cb("adm:f:pend", "files")
async def adm_pending(client, cq, args):
    idx = int(args[0]) if args and args[0].isdigit() else 0
    rows = await files.list_by_status("pending", idx, 1)
    if not rows and idx:
        rows, idx = await files.list_by_status("pending", 0, 1), 0
    if not rows:
        await tg.show(cq, "✅ No pending files.", kb(back("adm:f")))
        return
    f = rows[0]
    await tg.show(cq, file_card(f), kb([btn("✅ Approve", f"adm:f:ap:{f['_id']}"), btn("❌ Reject", f"adm:f:rj:{f['_id']}")],
                                       [btn("👁 Preview", f"adm:f:pv:{f['_id']}"), btn("⏭ Skip", f"adm:f:pend:{idx + 1}")], back("adm:f")))


async def _decide_file(client, cq, token, approve: bool):
    f = await (files.approve if approve else files.reject)(token, cq.from_user.id)
    if not f:
        return ("Already handled.", True)
    if f.get("owner_id"):
        owner = await users.get(f["owner_id"]) or {}
        lang = owner.get("lang", "en")
        name = esc(trunc(f.get("file_name") or f["file_type"], 60))
        markup = kb([btn(t(lang, "get_link"), f"sh:get:{token}")]) if approve else None
        await tg.notify(client, f["owner_id"], t(lang, "approved" if approve else "rejected", name=name), markup)
    await logs.activity(cq.from_user.id, "file_approve" if approve else "file_reject", token)
    try:                                     # submission notifications are media messages: just clear the buttons
        if cq.message.caption is not None or cq.message.media:
            await cq.message.edit_reply_markup(None)
            await cq.message.reply_text(("✅ Approved " if approve else "❌ Rejected ") + f"<code>{token}</code>")
        else:
            await adm_pending(client, cq, ["0"])
    except Exception:
        pass
    return "Approved." if approve else "Rejected."


@router.cb("adm:f:ap", "files")
async def adm_approve(client, cq, args):
    return await _decide_file(client, cq, args[0], True)


@router.cb("adm:f:rj", "files")
async def adm_reject(client, cq, args):
    return await _decide_file(client, cq, args[0], False)


@router.cb("adm:f:pv", "files")
async def adm_preview(client, cq, args):
    f = await files.get(args[0])
    if not f:
        return ("File not found.", True)
    await tg.safe(client.send_cached_media, cq.from_user.id, f["file_id"], caption=f"<code>{f['_id']}</code>")


@router.cb("adm:f:list", "files")
async def adm_recent_files(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    total = await files.count()
    rows = await files.list_recent(page * PER, PER)
    await tg.show(cq, f"📁 <b>Recent files</b> — page {page + 1}/{pages(total, PER)} ({total})",
                  kb(*[[btn(f"{trunc(f.get('file_name') or f.get('caption') or f['file_type'], 30)} · {f['status'][:4]}", f"adm:f:view:{f['_id']}")] for f in rows],
                     pager("adm:f:list", page, total, PER), back("adm:f")))


@router.cb("adm:f:view", "files")
async def adm_file_view(client, cq, args):
    f = await files.get(args[0])
    if not f:
        return ("File not found.", True)
    vis = "premium" if f.get("visibility") != "premium" else "public"
    await tg.show(cq, file_card(f), kb([btn(f"🔒 Make {vis}", f"adm:f:vis:{f['_id']}:{vis}"), btn("🗑 Delete", f"adm:f:rm:{f['_id']}")],
                                       [btn("👁 Preview", f"adm:f:pv:{f['_id']}")], back("adm:f:list:0")))


@router.cb("adm:f:vis", "files")
async def adm_file_vis(client, cq, args):
    if args[1] in ("public", "premium"):
        await files.set_visibility(args[0], args[1])
    await adm_file_view(client, cq, [args[0]])


@router.cb("adm:f:rm", "files")
async def adm_file_delete(client, cq, args):
    ok = await files.delete(args[0])
    await tg.show(cq, "🗑 File deleted." if ok else "File not found.", kb(back("adm:f")))


@router.cb("adm:f:del", "files")
async def adm_del_ask(client, cq, args):
    await adminui.ask(cq, "adm_f_del", "🗑 Send the file <b>token</b> to delete:")


@router.on_input("adm_f_del", "files")
async def in_delete(client, message, ctx):
    ok = await files.delete((message.text or "").strip())
    await message.reply_text("🗑 File deleted." if ok else "❌ No file with that token.", reply_markup=kb(back("adm:f")))


# ------------------------------------------------------------------ sharing
adminui.number_setting("adm_s_q", "free_quota", "Default free share quota (applies to NEW users)", 0, 1000, "adm:s", "sharing")


@router.cb("adm:s", "sharing")
async def adm_sharing(client, cq, args):
    on = await settings.get("sharing_enabled")
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    await tg.show(cq, f"🔗 <b>Sharing Management</b>\n\nSharing: {onoff(on)}\nDefault free quota: <b>{await settings.get('free_quota')}</b>\n"
                      f"Shares today: <b>{await sharing.count(None, since)}</b> · total: {await sharing.count()}\n\n"
                      "Per-user limits, resets and unlimited access are on each user's card (User Management).",
                  kb([btn(f"🔘 Sharing: {onoff(on)}", "adm:s:tog")], [btn("✏️ Default free quota", "adm:s:q")],
                     [btn("♻️ Reset ALL users' quota", "adm:s:ra")], [btn("📜 Recent shares", "adm:s:hist")], back()))


@router.cb("adm:s:tog", "sharing")
async def adm_sharing_toggle(client, cq, args):
    await settings.toggle("sharing_enabled")
    await adm_sharing(client, cq, args)


@router.cb("adm:s:q", "sharing")
async def adm_sharing_quota(client, cq, args):
    await adminui.number_prompt(cq, "adm_s_q", "Default free share quota", await settings.get("free_quota"), 0, 1000)


@router.cb("adm:s:ra", "sharing")
async def adm_reset_all_ask(client, cq, args):
    await tg.show(cq, "⚠️ Reset the share quota of <b>every non-unlimited user</b> to the default?",
                  kb([btn("✅ Yes, reset all", "adm:s:ra2"), btn("✖️ No", "adm:s")]))


@router.cb("adm:s:ra2", "sharing")
async def adm_reset_all(client, cq, args):
    n = await users.reset_all_free_quota()
    await tg.show(cq, f"✅ Quota reset for <b>{n}</b> users.", kb(back("adm:s")))


@router.cb("adm:s:hist", "sharing")
async def adm_recent_shares(client, cq, args):
    rows = await sharing.history(None, 0, 12)
    lines = ["📜 <b>Recent shares</b>", ""] + [
        f"{fmt_dt(r['ts'])} · <code>{r['user_id']}</code> · {esc(trunc(r.get('file_name') or r['file_token'], 30))}" for r in rows] if rows else ["No shares yet."]
    await tg.show(cq, "\n".join(lines), kb(back("adm:s")))
