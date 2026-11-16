"""Auto caption: every new file posted in the channel gets the ROAROIC links design."""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import ChatAdminRequired, FloodWait, MessageNotModified, RPCError

import config
from utils.captioning import compute_caption

log = logging.getLogger(__name__)
_lock = asyncio.Lock()


async def _is_source(_, __, message):
    if message.chat is None:
        return False
    return not config.SOURCE_CHANNELS or message.chat.id in config.SOURCE_CHANNELS


source_chat = filters.create(_is_source, "source_chat")
MEDIA = filters.document | filters.video | filters.audio | filters.photo | filters.animation | filters.voice


@Client.on_message(filters.channel & source_chat & MEDIA)
async def on_channel_media(client, message):
    cap = message.caption
    media = next((getattr(message, a) for a in ("document", "video", "audio", "animation", "voice", "photo")
                  if getattr(message, a, None)), None)
    new_caption = compute_caption(cap.html if cap else "", getattr(media, "file_name", None))
    async with _lock:                                  # gentle on flood limits during bulk uploads
        for _ in range(2):
            try:
                await client.edit_message_caption(message.chat.id, message.id, new_caption)
                break
            except MessageNotModified:
                break
            except FloodWait as e:
                await asyncio.sleep(int(getattr(e, "value", 1)) + 1)
            except ChatAdminRequired:
                log.error("Edit failed in %s: bot needs the 'Edit messages' admin right", message.chat.id)
                break
            except RPCError as e:
                log.error("Edit failed in %s: %s", message.chat.id, type(e).__name__)
                break
        await asyncio.sleep(0.6)
