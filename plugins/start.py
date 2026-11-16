"""/start, /preview (see the caption design), /id (shows a chat id)."""
from pyrogram import Client, filters

import config
from utils.captioning import compute_caption


@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await message.reply_text(f"✅ <b>{config.BOT_NAME}</b> is running.\n\nIt adds the ROAROIC caption to every file posted in "
                             "the channel where I am admin (with <i>Edit messages</i> right).\n\n/preview – see the design\n"
                             "/oldposts – update files already in the channel (owner)")


@Client.on_message(filters.command("preview") & filters.private)
async def preview_cmd(client, message):
    await message.reply_text(compute_caption("Sample Movie (2024) 1080p WEB-DL", None), disable_web_page_preview=True)


@Client.on_message(filters.command("id"))
async def id_cmd(client, message):
    await message.reply_text(f"<code>{message.chat.id}</code>")
