from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def btn(text: str, data: str | None = None, url: str | None = None):
    return InlineKeyboardButton(text, callback_data=data) if data is not None else InlineKeyboardButton(text, url=url)


def kb(*rows):
    return InlineKeyboardMarkup([list(r) for r in rows if r])


def pager(prefix: str, page: int, total: int, per_page: int):
    """Prev/next row for callback `prefix:<page>`."""
    row = []
    if page > 0:
        row.append(btn("⬅️ Prev", f"{prefix}:{page - 1}"))
    if (page + 1) * per_page < total:
        row.append(btn("Next ➡️", f"{prefix}:{page + 1}"))
    return row


def pages(total: int, per_page: int) -> int:
    return max(1, -(-total // per_page))
