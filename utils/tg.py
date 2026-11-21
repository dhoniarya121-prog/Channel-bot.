"""Thin helpers that turn plain data into Pyrogram objects (pyrogram is imported lazily)."""
import inspect

from utils.buttons import build_rows, color_for


def _colored_button(text: str, url: str, slot: dict):
    """URL button with an automatic colour; falls back to a plain button if this Pyrogram has no `style`."""
    from pyrogram.types import InlineKeyboardButton
    label = slot["prefix"] + text
    style = slot["style"]
    if style:
        try:
            from pyrogram import enums
            value = getattr(enums, "ButtonStyle")[style.upper()]
        except Exception:
            value = style
        try:
            return InlineKeyboardButton(label, url=url, style=value)
        except TypeError:
            pass
    return InlineKeyboardButton(label, url=url)


def url_markup(buttons: list[dict], per_row: int = 1):
    """Channel post buttons -> InlineKeyboardMarkup (None when there are no buttons).
    Buttons are coloured automatically, cycling through 5 colours in order."""
    if not buttons:
        return None
    from pyrogram.types import InlineKeyboardMarkup
    rows, n = [], 0
    for row in build_rows(buttons, per_row):
        out = []
        for b in row:
            out.append(_colored_button(b["text"], b["url"], color_for(n)))
            n += 1
        rows.append(out)
    return InlineKeyboardMarkup(rows)


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
