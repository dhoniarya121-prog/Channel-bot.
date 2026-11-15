"""Admin: statistics, admin permissions, database backup, logs, status/restart."""
import logging
import os
import signal
import sys

import config
from database import admins, files, logs, referrals, requests, settings, sharing, users
from keyboards.common import btn, kb, pager
from utils import adminui, health, lifecycle, router, state, tg, workers
from utils.adminui import back, onoff
from utils.text import esc, fmt_dt, trunc, utcnow
from datetime import timedelta

log = logging.getLogger(__name__)


# ============================================================ statistics
@router.cb("adm:st", "stats")
async def adm_stats(client, cq, args):
    s = await users.stats()
    now = utcnow()
    d1, d7 = now - timedelta(days=1), now - timedelta(days=7)
    from database import mongo
    refs = mongo.col(mongo.REFERRALS)
    await tg.show(cq, "📈 <b>Statistics</b>\n\n"
                      f"<b>Users</b>: {s['total']} total · {s['verified']} verified · {s['premium']} premium · {s['banned']} banned · {s['blocked']} blocked bot\n"
                      f"New: {s['new_24h']} (24h) · {s['new_7d']} (7d)\nActive: {s['active_24h']} (24h) · {s['active_7d']} (7d)\n\n"
                      f"<b>Files</b>: {await files.count('approved')} approved · {await files.count('pending')} pending · {await files.count('rejected')} rejected\n\n"
                      f"<b>Shares</b>: {await sharing.count()} total · {await sharing.count(None, d1)} (24h) · {await sharing.count(None, d7)} (7d)\n\n"
                      f"<b>Referrals</b>: {await refs.count_documents({})} total · {await refs.count_documents({'status': 'rewarded'})} rewarded\n"
                      f"<b>Requests</b>: {await requests.count('pending')} pending · {await requests.count('approved')} approved",
                  kb([btn("🔄 Refresh", "adm:st")], back()))


# ============================================================ admin permissions (owner only)
@router.cb("adm:ad", "owner")
async def adm_admins(client, cq, args):
    rows = await admins.list_all()
    owners = ", ".join(f"<code>{o}</code>" for o in sorted(config.OWNER_IDS))
    await tg.show(cq, f"👮 <b>Admin Permissions</b>\n\nOwners: {owners}\nAdmins: <b>{len(rows)}</b>",
                  kb(*[[btn(f"👮 {a['_id']} · {len(a.get('perms', []))} perms", f"adm:ad:v:{a['_id']}")] for a in rows],
                     [btn("➕ Add admin", "adm:ad:add")], back()))


async def _admin_card(cq, uid: int):
    a = await admins.get(uid)
    if not a:
        await tg.show(cq, "Admin not found.", kb(back("adm:ad")))
        return
    u = await users.get(uid) or {}
    perms = a.get("perms", [])
    rows, line = [], []
    for p in admins.PERMS:
        line.append(btn(("✅ " if p in perms else "❌ ") + p, f"adm:ad:t:{uid}:{p}"))
        if len(line) == 2:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    await tg.show(cq, f"👮 Admin <b>{esc(u.get('first_name') or uid)}</b> (<code>{uid}</code>)\nAdded: {fmt_dt(a.get('added_at'))}\n\nTap a permission to toggle it.",
                  kb(*rows, [btn("🗑 Remove admin", f"adm:ad:rm:{uid}")], back("adm:ad")))


@router.cb("adm:ad:v", "owner")
async def adm_admin_view(client, cq, args):
    await _admin_card(cq, int(args[0]))


@router.cb("adm:ad:t", "owner")
async def adm_admin_toggle(client, cq, args):
    if await admins.toggle_perm(int(args[0]), args[1]) is None:
        return ("Unknown admin or permission.", True)
    await _admin_card(cq, int(args[0]))


@router.cb("adm:ad:rm", "owner")
async def adm_admin_remove(client, cq, args):
    await admins.remove(int(args[0]))
    await adm_admins(client, cq, [])
    return "Admin removed."


@router.cb("adm:ad:add", "owner")
async def adm_admin_add(client, cq, args):
    await adminui.ask(cq, "adm_ad_add", "➕ Send the <b>user ID or @username</b> of the new admin (they must have started the bot):")


@router.on_input("adm_ad_add", "owner")
async def in_admin_add(client, message, ctx):
    u = await users.find(message.text or "")
    if not u:
        await message.reply_text("❌ User not found. They must start the bot first.")
        return
    if admins.is_owner(u["_id"]):
        await message.reply_text("They are an owner already.")
        return
    new = await admins.add(u["_id"], message.from_user.id)
    await message.reply_text(f"✅ {'Admin added' if new else 'Already an admin'}: <code>{u['_id']}</code>. Default permissions applied.",
                             reply_markup=kb([btn("👮 Permissions", f"adm:ad:v:{u['_id']}")], back("adm:ad")))


# ============================================================ backup
@router.cb("adm:bk", "backup")
async def adm_backup(client, cq, args):
    auto = await settings.get("auto_backup")
    await tg.show(cq, "💾 <b>Database Backup</b>\n\nCreates a gzip JSON export of all collections (logs excluded) and sends it to you here.\n"
                      f"Automatic daily backup to owners: {onoff(auto)}\n\n⚠️ Backups contain user data – keep them private.",
                  kb([btn("💾 Create backup now", "adm:bk:now")], [btn(f"⏰ Daily auto-backup: {onoff(auto)}", "adm:bk:auto")], back()))


@router.cb("adm:bk:now", "backup")
async def adm_backup_now(client, cq, args):
    await cq.answer("Creating backup…")
    n = await workers.send_backup(client, cq.from_user.id)
    await tg.reply(cq, f"✅ Backup sent ({n} file(s))." if n else "❌ Backup failed – see logs.")


@router.cb("adm:bk:auto", "backup")
async def adm_backup_auto(client, cq, args):
    await settings.toggle("auto_backup")
    await adm_backup(client, cq, args)


# ============================================================ logs
@router.cb("adm:lg", "logs")
async def adm_logs(client, cq, args):
    await tg.show(cq, "🐞 <b>Bot Logs</b>\n\nEntries are kept for 30 days. Secrets are redacted before storage.",
                  kb([btn("🐞 Errors", "adm:lg:e:0"), btn("📜 Warnings & errors", "adm:lg:a:0")],
                     [btn("👤 User activity", "adm:lg:act:0")], [btn("🧹 Clear logs (owner)", "adm:lg:clr")], back()))


async def _log_page(cq, errors_only: bool, page: int, prefix: str):
    rows, total = await logs.recent(errors_only, page * 4, 4)
    lines = [f"{'🐞 Errors' if errors_only else '📜 Logs'} — {total} entries", ""]
    for r in rows:
        lines.append(f"<b>{r['level']}</b> · {fmt_dt(r['ts'])} · {esc(r['module'])}\n<pre>{esc(trunc(r['message'], 500))}</pre>")
    if not rows:
        lines.append("Nothing logged. 🎉")
    await tg.show(cq, "\n".join(lines), kb(pager(prefix, page, total, 4), back("adm:lg")))


@router.cb("adm:lg:e", "logs")
async def adm_log_errors(client, cq, args):
    await _log_page(cq, True, int(args[0]) if args and args[0].isdigit() else 0, "adm:lg:e")


@router.cb("adm:lg:a", "logs")
async def adm_log_all(client, cq, args):
    await _log_page(cq, False, int(args[0]) if args and args[0].isdigit() else 0, "adm:lg:a")


@router.cb("adm:lg:act", "logs")
async def adm_log_activity(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    rows, total = await logs.user_activity(None, page * 10, 10)
    lines = [f"👤 <b>User activity</b> ({total})", ""] + [
        f"{fmt_dt(r['ts'])} · <code>{r['user_id']}</code> · {esc(r['action'])} {esc(r.get('detail', ''))}" for r in rows] if rows else ["👤 No activity yet."]
    await tg.show(cq, "\n".join(lines), kb(pager("adm:lg:act", page, total, 10), back("adm:lg")))


@router.cb("adm:lg:clr", "owner")
async def adm_log_clear(client, cq, args):
    await tg.show(cq, "⚠️ Delete all stored error/warning logs?", kb([btn("✅ Yes, clear", "adm:lg:clr2"), btn("✖️ No", "adm:lg")]))


@router.cb("adm:lg:clr2", "owner")
async def adm_log_clear_do(client, cq, args):
    n = await logs.clear()
    await tg.show(cq, f"🧹 Cleared {n} log entries.", kb(back("adm:lg")))


# ============================================================ status / restart
@router.cb("adm:sys", "system")
async def adm_system(client, cq, args):
    snap = await health.snapshot()
    await tg.show(cq, f"🔄 <b>Status</b>\n\nVersion: {config.VERSION}\nPython: {sys.version.split()[0]}\nUptime: {snap['uptime']}\n"
                      f"Database: {'✅ ' + str(snap['db_ms']) + ' ms' if snap['db_ok'] else '❌ unreachable'}\n"
                      f"Memory: {snap['memory_mb'] or '?'} MB\nSeconds since last update: {snap['idle_s']}",
                  kb([btn("🔄 Refresh status", "adm:sys"), btn("♻️ Restart bot", "adm:sys:rs")], back()))


@router.cb("adm:sys:rs", "system")
async def adm_restart_ask(client, cq, args):
    await tg.show(cq, "⚠️ Restart the bot process now? Running broadcasts will stop; pending prompts are forgotten.",
                  kb([btn("✅ Restart", "adm:sys:rs2"), btn("✖️ Cancel", "adm:sys")]))


@router.cb("adm:sys:rs2", "system")
async def adm_restart(client, cq, args):
    await tg.show(cq, "♻️ Restarting… I'll be back in a few seconds.")
    log.warning("Restart requested by admin %s", cq.from_user.id)
    lifecycle.RESTART_REQUESTED = True
    os.kill(os.getpid(), signal.SIGTERM)       # same path as Render's own SIGTERM: graceful shutdown in bot.py
