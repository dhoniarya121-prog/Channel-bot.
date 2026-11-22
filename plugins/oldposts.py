"""Old posts. Easiest way: /menu -> My Channels -> (channel) -> ▶️ Run on old posts.

Command version:
  /oldposts https://t.me/c/1234567890/900        -> posts 1..900 of that channel
  /oldposts -1001234567890 100 900               -> posts 100..900
  /oldposts @channelname 500                     -> posts 1..500
  /stopold                                       -> stop your running job
The channel must be in your list (➕ Add Channel). It applies captions + buttons using that channel's settings.
"""
from pyrogram import Client, filters

import config
from utils import jobs, runner, store
from utils.buttons import parse_post_link
from utils.oldposts import parse_range


async def _is_allowed(_, __, message):
    u = getattr(message, "from_user", None)
    return bool(u) and store.user_allowed(u.id)


allowed = filters.create(_is_allowed, "allowed")
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


@Client.on_message(filters.command("oldposts") & filters.private & allowed)
async def oldposts_cmd(client, message):
    uid = message.from_user.id
    store.set_user(uid)
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
    if store.get(chat_id) is None or not store.can_manage(uid, chat_id):
        await message.reply_text("❌ That channel is not in your list. Add it first: /menu → ➕ Add Channel.")
        return
    if await runner.start_job(client, chat_id, "both", start, end, uid, message) is None:
        await message.reply_text("⚠️ A job is already running. /stopold to stop it.")


@Client.on_message(filters.command("stopold") & filters.private & allowed)
async def stop_cmd(client, message):
    if not jobs.request_stop(message.from_user.id):
        await message.reply_text("⚠️ That job was started by someone else.")
        return
    await message.reply_text("⏹ Stopping after the current post…")
