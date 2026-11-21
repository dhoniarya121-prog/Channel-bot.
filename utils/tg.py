"""Thin helpers that turn plain data into Pyrogram objects (pyrogram is imported lazily)."""
import inspect

from utils.buttons import build_rows, color_for


def _make_button(text: str, slot: dict, **kw):
    """Inline button with an automatic colour; falls back to a plain button if this Pyrogram has no `style`."""
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
            return InlineKeyboardButton(label, style=value, **kw)
        except TypeError:
            pass
    return InlineKeyboardButton(label, **kw)


def colors_supported() -> bool:
    """True when the installed Pyrogram/Kurigram can send coloured (styled) inline buttons."""
    try:
        from pyrogram.types import InlineKeyboardButton
        return "style" in inspect.signature(InlineKeyboardButton.__init__).parameters
    except Exception:
        return False


def _colored_button(text: str, url: str, slot: dict):
    return _make_button(text, slot, url=url)


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
    """Menu rows [{text, data} | {text, url}] -> InlineKeyboardMarkup. Every button is coloured, cycling."""
    from pyrogram.types import InlineKeyboardMarkup
    out, n = [], 0
    for row in rows:
        line = []
        for b in row:
            kw = {"url": b["url"]} if "url" in b else {"callback_data": b["data"]}
            line.append(_make_button(b["text"], color_for(n), **kw))
            n += 1
        out.append(line)
    return InlineKeyboardMarkup(out)


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
