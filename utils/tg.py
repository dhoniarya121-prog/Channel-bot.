"""Thin helpers that turn plain data into Pyrogram objects (pyrogram is imported lazily)."""
import inspect

from utils.buttons import build_rows


def url_markup(buttons: list[dict], per_row: int = 1):
    """Channel post buttons -> InlineKeyboardMarkup (None when there are no buttons)."""
    if not buttons:
        return None
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
                                 for row in build_rows(buttons, per_row)])


def menu_markup(rows: list[list[dict]]):
    """Menu rows [{text, data} | {text, url}] -> InlineKeyboardMarkup."""
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[InlineKeyboardButton(b["text"], url=b["url"]) if "url" in b
                                  else InlineKeyboardButton(b["text"], callback_data=b["data"]) for b in row]
                                 for row in rows])


def forwarded_chat(message):
    """Chat a message was forwarded from (works with old `forward_from_chat` and new `forward_origin`)."""
    chat = getattr(message, "forward_from_chat", None)
    if chat is None:
        chat = getattr(getattr(message, "forward_origin", None), "chat", None)
    return chat


def nopreview(fn) -> dict:
    """Keyword that turns off link previews, whichever name this Pyrogram/Kurigram version uses for it."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if "disable_web_page_preview" in params:
        return {"disable_web_page_preview": True}
    if "link_preview_options" in params:
        try:
            from pyrogram.types import LinkPreviewOptions
            return {"link_preview_options": LinkPreviewOptions(is_disabled=True)}
        except Exception:
            return {}
    return {}
