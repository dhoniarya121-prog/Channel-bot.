"""Force-subscribe gate shared by all user-facing flows."""
import time

from database import admins, channels, settings
from keyboards.user import fsub_kb
from utils import forcesub, tg
from utils.i18n import t

_OK: dict = {}          # (user_id, chat_id) -> monotonic expiry of a positive membership result
OK_TTL = 60


def forget(user_id: int) -> None:
    for k in [k for k in _OK if k[0] == user_id]:
        _OK.pop(k, None)


async def missing_channels(client, user_id: int, fresh: bool = False) -> list[dict]:
    if not await settings.get("forcesub_enabled"):
        return []
    chans = await channels.list_role("fsub")
    if not chans:
        return []
    if fresh:
        forget(user_id)
    now = time.monotonic()

    async def checker(ch, uid):
        if _OK.get((uid, ch["chat_id"]), 0) > now:
            return True
        r = await tg.is_member(client, ch, uid)
        if r is True:
            _OK[(uid, ch["chat_id"])] = now + OK_TTL
        return r
    return (await forcesub.evaluate(user_id, chans, checker)).missing


async def fsub_gate(client, target, user, payload: str = "", lang: str = "en", fresh: bool = False) -> bool:
    """True = user may continue. Otherwise the join prompt has been sent."""
    if await admins.is_admin(user.id):
        return True
    missing = await missing_channels(client, user.id, fresh)
    if not missing:
        return True
    await tg.reply(target, t(lang, "fsub_prompt"), fsub_kb(lang, missing, payload))
    return False
