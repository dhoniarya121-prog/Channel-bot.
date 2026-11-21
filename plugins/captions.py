"""Auto mode: every new post in a channel gets that channel's caption design and/or link buttons.
Each channel uses its own settings from the menu (falling back to the default settings)."""
import logging

from pyrogram import Client, filters

import config
from utils import runner, store

log = logging.getLogger(__name__)


async def _is_source(_, __, message):
    if message.chat is None:
        return False
    return not config.SOURCE_CHANNELS or message.chat.id in config.SOURCE_CHANNELS


source_chat = filters.create(_is_source, "source_chat")


@Client.on_message(filters.channel & source_chat & ~filters.service)
async def on_channel_post(client, message):
    _, created = store.ensure_channel(message.chat.id, message.chat.title)
    if created:                                     # first post seen from a new channel: tell the owner once
        for uid in config.OWNER_IDS:
            try:
                await client.send_message(uid, f"📡 New channel detected: <b>{message.chat.title}</b>\n"
                                               "It uses the default settings. Open /menu → My Channels to customise it.")
            except Exception:
                pass
    eff = store.effective(message.chat.id)
    if eff["caption"] or (eff["buttons_on"] and eff["buttons"]):
        await runner.auto_edit(client, message)
