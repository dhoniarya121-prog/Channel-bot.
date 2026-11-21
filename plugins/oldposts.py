"""Old posts. Easiest way: /menu -> My Channels -> (channel) -> ▶️ Run on old posts.

Command version (owner):
  /oldposts https://t.me/c/1234567890/900        -> posts 1..900 of that channel
  /oldposts -1001234567890 100 900               -> posts 100..900
  /oldposts @channelname 500                     -> posts 1..500
  /stopold                                       -> stop the running job
It applies captions + buttons using that channel's own settings.
"""
from pyrogram import Client, filters

import config
from utils import jobs, runner
from utils.buttons import parse_post_link
from utils.oldposts import parse_range

owner = filters.user(list(config.OWNER_IDS)) if config.OWNER_IDS else filters.user([0])
USAGE = ("Use:\n<code>/oldposts https://t.me/c/1234567890/900</code>\n<code>/oldposts -1001234567890 100 900</code>\n"
         "<code>/oldposts @channelname 500</code>\n\nOr use the buttons: /menu → My Channels → ▶️ Run on old posts")


def parse_args(args: list[str]):
    """Returns (chat, start, end) or None."""
    if not args:
        return None
    ref = parse_post_link(args[0])
    if ref:
        return ref[0], 1, ref[1]
    chat = args[0]
    chat = int(chat) if chat.lstrip("-").isdigit() else chat
    rng = parse_range(" ".join(args[1:]))
    return (chat, *rng) if rng else None


@Client.on_message(filters.command("oldposts") & filters.private & owner)
async def oldposts_cmd(client, message):
    parsed = parse_args(message.command[1:])
    if not parsed:
        await message.reply_text("⚠️ " + USAGE)
        return
    chat, start, end = parsed
    try:
        chat_id = (await client.get_chat(chat)).id             # @username -> numeric id (settings are stored by id)
    except Exception:
        await message.reply_text("❌ I can't open that channel. Is the bot admin there?")
        return
    if await runner.start_job(client, chat_id, "both", start, end, message.from_user.id, message) is None:
        await message.reply_text("⚠️ A job is already running. /stopold to stop it.")


@Client.on_message(filters.command("stopold") & filters.private & owner)
async def stop_cmd(client, message):
    jobs.request_stop()
    await message.reply_text("⏹ Stopping after the current post…")
