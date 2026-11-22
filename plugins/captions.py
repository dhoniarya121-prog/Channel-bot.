"""Auto mode: every new post in a channel gets that channel's caption design and/or link buttons.
Each channel uses its owner's settings (the channel's own, else the owner's defaults)."""
import logging

from pyrogram import Client, filters

import config
from utils import runner, store

log = logging.getLogger(__name__)
_told: set[int] = set()          # unclaimed channels the admins were already told about (once per run)


async def _is_source(_, __, message):
    if message.chat is None:
        return False
    return not config.SOURCE_CHANNELS or message.chat.id in config.SOURCE_CHANNELS


source_chat = filters.create(_is_source, "source_chat")


async def _tell_admins(client, text: str) -> None:
    for uid in config.OWNER_IDS:
        try:
            await client.send_message(uid, text)
        except Exception:
            pass


@Client.on_message(filters.channel & source_chat & ~filters.service)
async def on_channel_post(client, message):
    chat = message.chat
    if store.get(chat.id) is None:
        if config.PUBLIC_MODE:
            # Nobody has added this channel yet: do nothing to it (it is not ours to edit).
            if chat.id not in _told:
                _told.add(chat.id)
                await _tell_admins(client, f"ℹ️ Post seen in <b>{chat.title}</b> (<code>{chat.id}</code>), but nobody has added "
                                           "this channel yet. Its admin can add it from the bot menu (➕ Add Channel).")
            return
        owner = next(iter(sorted(config.OWNER_IDS)), None)     # private mode: owner's channels register themselves
        store.ensure_channel(chat.id, chat.title, owner=owner)
        await _tell_admins(client, f"📡 New channel detected: <b>{chat.title}</b>\n"
                                   "It uses your default settings. Open /menu → My Channels to customise it.")
    else:
        store.ensure_channel(chat.id, chat.title)
    eff = store.effective(chat.id)
    if eff["caption"] or (eff["buttons_on"] and eff["buttons"]):
        await runner.auto_edit(client, message)
