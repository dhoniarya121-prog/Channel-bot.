from database import settings
from keyboards.common import btn, kb
from utils.buttons import build_rows


async def channel_markup(force: bool = False):
    """Inline URL keyboard attached to channel posts, or None when the feature is off / empty."""
    buttons = await settings.get("channel_buttons")
    if not buttons or not (force or await settings.get("buttons_enabled")):
        return None
    rows = build_rows(buttons, await settings.get("buttons_per_row"))
    return kb(*[[btn(b["text"], url=b["url"]) for b in row] for row in rows])
