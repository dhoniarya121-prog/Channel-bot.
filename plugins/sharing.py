"""File submission, approval notifications, share-link creation, direct file delivery."""
import logging

from pyrogram import Client, filters

from database import admins, files, logs, settings, sharing, users
from keyboards.common import btn, kb, pager
from keyboards.user import get_link_kb, home_btn
from utils import delivery, guards, router, state, tg
from utils.i18n import t
from utils.links import share_link
from utils.text import esc, trunc
from utils.views import quota_text

log = logging.getLogger(__name__)
PER_PAGE = 6
SHARE_REASONS = {"disabled": "share_disabled", "no_file": "share_nofile", "no_access": "share_noaccess",
                 "premium_only": "share_noaccess", "pending": "share_pending", "limit": "share_limit",
                 "banned": "share_noperm", "no_permission": "share_noperm", "no_user": "share_nofile"}


async def notify_admins_new_file(client, f: dict, owner: dict):
    card = (f"📥 <b>New file submission</b>\n\nFrom: {esc(owner.get('first_name'))} (<code>{owner['_id']}</code>)\n"
            f"Name: {esc(trunc(f.get('file_name') or '-', 80))}\nType: {f['file_type']}")
    markup = kb([btn("✅ Approve", f"adm:f:ap:{f['_id']}"), btn("❌ Reject", f"adm:f:rj:{f['_id']}")])
    for aid in await admins.all_ids():
        if await admins.has_perm(aid, "files"):
            try:
                await tg.safe(client.send_cached_media, aid, f["file_id"], caption=card[:1024], reply_markup=markup)
            except Exception:
                await tg.notify(client, aid, card, markup)


@Client.on_message(filters.private & filters.media & ~filters.service, group=1)
async def submit_media(client, message):
    user = message.from_user
    media = tg.extract_media(message)
    if not media:
        return
    doc = await users.get(user.id)
    lang = doc.get("lang", "en")
    admin = await admins.is_admin(user.id)
    if not users.has_perm(doc, "submit") and not admin:
        await message.reply_text(t(lang, "submit_noperm"))
        return
    if not await guards.fsub_gate(client, message, user, lang=lang):
        return
    if not admin and await settings.get("require_verification") and not doc.get("verified"):
        await message.reply_text(t(lang, "verify_need"))
        return
    auto = admin or await settings.get("auto_approve_files")
    f, created = await files.submit(user.id, media, auto)
    if not created:
        markup = get_link_kb(lang, f["_id"]) if f["status"] == "approved" else None
        await message.reply_text(t(lang, "submit_dup"), reply_markup=markup)
        return
    await logs.activity(user.id, "file_submit", f["_id"])
    if auto:
        await message.reply_text(t(lang, "submit_auto"), reply_markup=get_link_kb(lang, f["_id"]))
    else:
        await message.reply_text(t(lang, "submit_received"))
        await notify_admins_new_file(client, f, doc)


@router.cb("u:submit")
async def cb_submit(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, t(doc.get("lang", "en"), "submit_prompt"), home_btn(doc.get("lang", "en")))


@router.cb("sh:get")
async def cb_share(client, cq, args):
    user = cq.from_user
    token = args[0] if args else ""
    doc = await users.get(user.id)
    lang = doc.get("lang", "en")
    admin = await admins.is_admin(user.id)
    if not await guards.fsub_gate(client, cq, user, lang=lang):
        return
    if not admin and await settings.get("require_verification") and not doc.get("verified"):
        return (t(lang, "verify_need").replace("<b>", "").replace("</b>", ""), True)
    res = await sharing.share_file(user.id, token, admin)
    if not res.ok:
        text = t(lang, SHARE_REASONS.get(res.reason, "share_nofile"))
        return (text.replace("<b>", "").replace("</b>", "")[:190], True)
    link = share_link(await tg.bot_username(client), token)
    if res.reason == "already":
        await tg.reply(cq, t(lang, "share_already", link=link))
    else:
        await logs.activity(user.id, "share", token)
        await tg.reply(cq, t(lang, "share_ok", link=link, quota=quota_text(await users.get(user.id))))


@router.cb("f:get")
async def cb_get_file(client, cq, args):
    user = cq.from_user
    doc = await users.get(user.id)
    lang = doc.get("lang", "en")
    if not await guards.fsub_gate(client, cq, user, lang=lang):
        return
    res = await delivery.deliver(client, doc, args[0] if args else "", await admins.is_admin(user.id))
    if res != "ok":
        text = t(lang, delivery.REASON_KEYS.get(res, "unavailable"))
        return (text.replace("<b>", "").replace("</b>", "")[:190], True)


async def my_files_view(doc: dict, page: int):
    lang = doc.get("lang", "en")
    rows, total = await files.list_by_owner(doc["_id"], page * PER_PAGE, PER_PAGE)
    if not total:
        return t(lang, "files_none"), home_btn(lang)
    lines, buttons = [t(lang, "files_head", n=total), ""], []
    for f in rows:
        lines.append(f"• {esc(trunc(f.get('file_name') or f.get('caption') or f['file_type'], 40))} — {t(lang, 'status_' + f['status'])}")
        if f["status"] == "approved":
            buttons.append([btn(f"🔗 {trunc(f.get('file_name') or f['file_type'], 30)}", f"sh:get:{f['_id']}")])
    buttons.append(pager("u:files", page, total, PER_PAGE))
    buttons.append([btn(t(lang, "back"), "u:home")])
    return "\n".join(lines), kb(*buttons)


@Client.on_message(filters.command("myfiles") & filters.private)
async def myfiles_cmd(client, message):
    text, markup = await my_files_view(await users.get(message.from_user.id), 0)
    await message.reply_text(text, reply_markup=markup)


@router.cb("u:files")
async def cb_myfiles(client, cq, args):
    page = int(args[0]) if args and args[0].isdigit() else 0
    text, markup = await my_files_view(await users.get(cq.from_user.id), page)
    await tg.show(cq, text, markup)


@router.cb("u:search")
async def cb_search(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, t(doc.get("lang", "en"), "search_prompt"), home_btn(doc.get("lang", "en")))
