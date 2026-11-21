"""/start for everyone else, /preview, /id. (The owner's /start and /menu are in plugins/panel.py.)"""
from pyrogram import Client, filters

import config
from utils.captioning import compute_caption

owner = filters.user(list(config.OWNER_IDS)) if config.OWNER_IDS else filters.user([0])


@Client.on_message(filters.command("start") & filters.private & ~owner)
async def start_cmd(client, message):
    await message.reply_text(f"✅ <b>{config.BOT_NAME}</b> is running.\n\nThis is a private channel helper bot.")


@Client.on_message(filters.command("preview") & filters.private & owner)
async def preview_cmd(client, message):
    await message.reply_text(compute_caption("Sample Movie (2024) 1080p WEB-DL", None), disable_web_page_preview=True)


@Client.on_message(filters.command("id"))
async def id_cmd(client, message):
    await message.reply_text(f"<code>{message.chat.id}</code>")
