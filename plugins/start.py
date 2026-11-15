"""/start, deep links (file + referral), verification, profile, language, help, user menu."""
import logging

import config
from pyrogram import Client, filters

from database import admins, referrals, settings, users, logs
from keyboards.user import home_btn, lang_kb, main_menu
from utils import delivery, guards, router, state, tg
from utils.i18n import t
from utils.links import valid_token
from utils.text import esc
from utils.views import dev, plan_text, profile_text, quota_text

log = logging.getLogger(__name__)


async def home_text(doc: dict) -> str:
    lang = doc.get("lang", "en")
    custom = ((await settings.get("start_message")) or {}).get(lang) or ""
    if custom:
        for k, v in {"{name}": esc(doc.get("first_name")), "{bot}": config.BOT_NAME,
                     "{quota}": quota_text(doc), "{plan}": plan_text(doc)}.items():
            custom = custom.replace(k, v)
        return custom
    return t(lang, "welcome", name=esc(doc.get("first_name")), bot=config.BOT_NAME,
             quota=quota_text(doc), plan=plan_text(doc))


async def show_home(target, doc: dict, user_id: int, edit: bool = False):
    admin = await admins.is_admin(user_id)
    markup = main_menu(doc.get("lang", "en"), bool(doc.get("verified")), admin)
    text = await home_text(doc)
    await (tg.show(target, text, markup) if edit else tg.reply(target, text, markup))


async def handle_payload(client, message, doc, payload: str):
    lang = doc.get("lang", "en")
    if payload.startswith("f_") and valid_token(payload[2:]):
        res = await delivery.deliver(client, doc, payload[2:], await admins.is_admin(doc["_id"]))
        if res != "ok":
            await message.reply_text(await delivery.reason_text(lang, res, await users.get(doc["_id"])))
        return res == "ok"
    return False


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user = message.from_user
    doc = await users.get(user.id)
    lang = doc.get("lang", "en")
    payload = message.command[1] if len(message.command) > 1 else ""
    if state.pop_new(user.id) and payload.startswith("r_"):
        res = await referrals.track(user.id, payload[2:])
        await logs.activity(user.id, "referral_track", res.status)
    state.clear_state(user.id)
    if not await guards.fsub_gate(client, message, user, payload[:40], lang):
        return
    if payload.startswith("f_"):
        if await handle_payload(client, message, doc, payload):
            return
    await show_home(message, doc, user.id)


@Client.on_message(filters.command(["menu", "home"]) & filters.private)
async def menu_cmd(client, message):
    await show_home(message, await users.get(message.from_user.id), message.from_user.id)


@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message):
    state.clear_state(message.from_user.id)
    doc = await users.get(message.from_user.id)
    await message.reply_text(t(doc.get("lang", "en"), "cancelled"))


@Client.on_message(filters.command(["help"]) & filters.private)
async def help_cmd(client, message):
    doc = await users.get(message.from_user.id)
    await message.reply_text(t(doc.get("lang", "en"), "help", dev=dev()), reply_markup=home_btn(doc.get("lang", "en")))


@Client.on_message(filters.command(["myinfo", "profile"]) & filters.private)
async def profile_cmd(client, message):
    doc = await users.get(message.from_user.id)
    await message.reply_text(profile_text(doc), reply_markup=home_btn(doc.get("lang", "en")))


@Client.on_message(filters.command("lang") & filters.private)
async def lang_cmd(client, message):
    doc = await users.get(message.from_user.id)
    await message.reply_text(t(doc.get("lang", "en"), "lang_choose"), reply_markup=lang_kb())


# ----------------------------------------------------------------- callbacks
@router.cb("u:home")
async def cb_home(client, cq, args):
    state.clear_state(cq.from_user.id)
    await show_home(cq, await users.get(cq.from_user.id), cq.from_user.id, edit=True)


@router.cb("u:profile")
async def cb_profile(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, profile_text(doc), home_btn(doc.get("lang", "en")))


@router.cb("u:help")
async def cb_help(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, t(doc.get("lang", "en"), "help", dev=dev()), home_btn(doc.get("lang", "en")))


@router.cb("u:lang")
async def cb_lang_menu(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, t(doc.get("lang", "en"), "lang_choose"), lang_kb())


@router.cb("lang")
async def cb_lang_set(client, cq, args):
    lang = args[0] if args and args[0] in ("en", "hi") else "en"
    await users.set_lang(cq.from_user.id, lang)
    doc = await users.get(cq.from_user.id)
    await show_home(cq, doc, cq.from_user.id, edit=True)
    return t(lang, "lang_set")


@router.cb("v:go")
async def cb_verify(client, cq, args):
    user = cq.from_user
    doc = await users.get(user.id)
    lang = doc.get("lang", "en")
    if doc.get("verified"):
        return t(lang, "already_verified")
    if not await guards.fsub_gate(client, cq, user, "", lang, fresh=True):
        return
    if await users.set_verified(user.id, True):
        reward = await referrals.reward_on_verify(user.id)
        if reward:
            parts = []
            if reward["quota"]:
                parts.append(t("en", "ref_reward_daily" if reward.get("mode") == "daily" else "ref_reward_quota", n=reward["quota"]))
            if reward["days"]:
                parts.append(t("en", "ref_reward_days", n=reward["days"]))
            rdoc = await users.get(reward["referrer_id"])
            await tg.notify(client, reward["referrer_id"],
                            t((rdoc or {}).get("lang", "en"), "ref_reward", reward=", ".join(parts) or "🎁"))
        await logs.activity(user.id, "verified")
    doc = await users.get(user.id)
    await show_home(cq, doc, user.id, edit=True)
    return t(lang, "verify_ok")


@router.cb("fs:r")
async def cb_fsub_refresh(client, cq, args):
    user = cq.from_user
    doc = await users.get(user.id)
    lang = doc.get("lang", "en")
    missing = await guards.missing_channels(client, user.id, fresh=True)
    if missing:
        return (t(lang, "fsub_still"), True)
    payload = args[0] if args else ""
    if payload.startswith("f_"):
        await handle_payload(client, cq.message, doc, payload)
    await show_home(cq, doc, user.id, edit=True)
