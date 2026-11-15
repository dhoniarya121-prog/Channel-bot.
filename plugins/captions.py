"""Automatic caption editor for files posted in the configured source channels."""
import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import ChatAdminRequired, MessageNotModified, RPCError

from database import channels, files, settings
from keyboards.channel import channel_markup
from utils import tg
from utils.captions import build_caption

log = logging.getLogger(__name__)
_edit_lock = asyncio.Lock()


async def _is_source(_, __, message):
    return message.chat is not None and await channels.get("source", message.chat.id) is not None


source_chat = filters.create(_is_source, "source_chat")
MEDIA = filters.document | filters.video | filters.audio | filters.photo | filters.animation | filters.voice


@Client.on_message(filters.channel & source_chat & MEDIA, group=0)
async def on_channel_media(client, message):
    media = tg.extract_media(message)
    if not media:
        return
    original_html = media.pop("caption_html")
    f, created = await files.add_channel_file(message.chat.id, message.id, media)
    if not created:
        return                                   # this post was already processed (e.g. update replay)
    auto = await settings.get("auto_caption")
    markup = await channel_markup()
    if not auto and not markup:
        return
    new_caption = None
    if auto:
        templates = await settings.get("caption_templates")
        template = templates.get(await settings.get("active_template")) or next(iter(templates.values()))
        new_caption = build_caption(original_html, template, await settings.get("links"),
                                    await settings.get("old_links"), media.get("file_name"))
    async with _edit_lock:                       # gentle on Telegram flood limits during bulk uploads
        try:
            if new_caption is not None:          # caption + permanent URL buttons in ONE edit
                await tg.safe(client.edit_message_caption, message.chat.id, message.id, new_caption, reply_markup=markup)
                await files.set_caption(f["_id"], new_caption)
            else:
                await tg.safe(client.edit_message_reply_markup, message.chat.id, message.id, markup)
        except MessageNotModified:
            pass
        except ChatAdminRequired:
            log.error("Edit failed in %s: bot lacks the 'Edit messages' right", message.chat.id)
        except RPCError as e:
            log.error("Edit failed in %s: %s", message.chat.id, type(e).__name__)
        await asyncio.sleep(0.6)
