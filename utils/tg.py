"""Pyrogram helpers: media extraction, safe sends/edits, membership checks, channel inspection."""
import asyncio
import logging

from pyrogram import enums
from pyrogram.errors import (ChatAdminRequired, FloodWait, InputUserDeactivated, MessageNotModified,
                             RPCError, UserIsBlocked, UserNotParticipant)
from pyrogram.types import CallbackQuery

from database import users

log = logging.getLogger(__name__)
MEDIA_ATTRS = ("document", "video", "audio", "animation", "voice", "video_note", "photo")
_ME: dict = {}


def flood_seconds(e) -> int:
    return int(getattr(e, "value", None) or getattr(e, "x", None) or 1)


async def safe(call, *args, retries: int = 2, **kw):
    """Run a Pyrogram coroutine function, sleeping through FloodWait."""
    for attempt in range(retries + 1):
        try:
            return await call(*args, **kw)
        except FloodWait as e:
            if attempt == retries:
                raise
            await asyncio.sleep(flood_seconds(e) + 1)


def extract_media(message) -> dict | None:
    for attr in MEDIA_ATTRS:
        m = getattr(message, attr, None)
        if m:
            cap = message.caption
            return {"file_id": m.file_id, "file_unique_id": m.file_unique_id, "file_type": attr,
                    "file_name": getattr(m, "file_name", None), "file_size": getattr(m, "file_size", None),
                    "caption": str(cap) if cap else "", "caption_html": cap.html if cap else ""}
    return None


async def show(target, text: str, kb=None) -> None:
    """Edit the callback message, or reply to a plain message."""
    text = text[:4000]
    try:
        if isinstance(target, CallbackQuery):
            await safe(target.message.edit_text, text, reply_markup=kb)
        else:
            await safe(target.reply_text, text, reply_markup=kb)
    except MessageNotModified:
        pass


async def reply(target, text: str, kb=None):
    msg = target.message if isinstance(target, CallbackQuery) else target
    return await safe(msg.reply_text, text[:4000], reply_markup=kb)


async def notify(client, user_id: int, text: str, kb=None) -> bool:
    try:
        await safe(client.send_message, user_id, text[:4000], reply_markup=kb)
        return True
    except (UserIsBlocked, InputUserDeactivated):
        await users.mark_blocked(user_id)
    except RPCError as e:
        log.info("notify failed for %s: %s", user_id, type(e).__name__)
    return False


async def bot_username(client) -> str:
    if "u" not in _ME:
        _ME["u"] = (await client.get_me()).username
    return _ME["u"]


async def is_member(client, ch: dict, user_id: int):
    """True / False / None (cannot verify - e.g. bot is not admin in that channel)."""
    try:
        m = await safe(client.get_chat_member, ch["chat_id"], user_id)
    except UserNotParticipant:
        return False
    except RPCError as e:
        log.warning("get_chat_member(%s) failed: %s", ch["chat_id"], type(e).__name__)
        return None
    if m.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
        return False
    if m.status == enums.ChatMemberStatus.RESTRICTED:
        return bool(getattr(m, "is_member", True))
    return True


async def inspect_channel(client, ref) -> dict:
    """Resolve a channel and report the bot's rights. Raises RPCError/ValueError for bad references."""
    chat = await client.get_chat(ref)
    info = {"chat_id": chat.id, "title": chat.title or str(chat.id), "username": chat.username or "",
            "private": not chat.username, "is_admin": False, "can_edit": False, "can_invite": False,
            "type": str(getattr(chat.type, "name", chat.type))}
    try:
        me = await client.get_chat_member(chat.id, "me")
    except RPCError:
        return info
    owner = me.status == enums.ChatMemberStatus.OWNER
    info["is_admin"] = owner or me.status == enums.ChatMemberStatus.ADMINISTRATOR
    priv = getattr(me, "privileges", None)
    info["can_edit"] = owner or bool(priv and getattr(priv, "can_edit_messages", False))
    info["can_invite"] = owner or bool(priv and getattr(priv, "can_invite_users", False))
    return info


async def export_invite(client, chat_id: int) -> str | None:
    try:
        return await safe(client.export_chat_invite_link, chat_id)
    except (RPCError, ChatAdminRequired):
        return None
