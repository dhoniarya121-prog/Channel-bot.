"""/start for people who may not use the bot (banned, or private mode), /preview, /id.
(Allowed users' /start and /menu are in plugins/panel.py.)"""
from pyrogram import Client, filters

import config
from utils import store, tg
from utils.captioning import compute_caption


async def _is_allowed(_, __, message):
    u = getattr(message, "from_user", None)
    return bool(u) and store.user_allowed(u.id)


allowed = filters.create(_is_allowed, "allowed")


@Client.on_message(filters.command(["start", "menu", "preview"]) & filters.private & ~allowed)
async def start_cmd(client, message):
    uid = message.from_user.id if message.from_user else 0
    if uid and store.is_banned(uid):
        await message.reply_text("🚫 You are not allowed to use this bot.")
        return
    await message.reply_text(f"✅ <b>{config.BOT_NAME}</b> is running.\n\nThis bot is private.\n"
                             f"Your ID: <code>{uid}</code>\n<i>If you are the owner, put this number in OWNER_ID and restart.</i>")


@Client.on_message(filters.command("preview") & filters.private & allowed)
async def preview_cmd(client, message):
    store.set_user(message.from_user.id)
    await message.reply_text(compute_caption("Sample Movie (2024) 1080p WEB-DL", None),
                             **tg.nopreview(message.reply_text))


@Client.on_message(filters.command("id"))
async def id_cmd(client, message):
    await message.reply_text(f"<code>{message.chat.id}</code>")
