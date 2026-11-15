"""File search (plain-text messages) with paginated results."""
import logging

from database import files, settings, users
from keyboards.common import btn, kb, pager
from utils import guards, router, tg
from utils.i18n import t
from utils.text import esc, trunc

log = logging.getLogger(__name__)
PAGE = 6
LAST_QUERY: dict[int, str] = {}


def build_results(lang: str, query: str, rows: list[dict], total: int, page: int):
    text = t(lang, "search_head", q=esc(trunc(query, 60)), n=total)
    buttons = []
    for f in rows:
        name = trunc(f.get("file_name") or f.get("caption") or "file", 34)
        buttons.append([btn(f"📥 {name}", f"f:get:{f['_id']}"), btn(t(lang, "share"), f"sh:get:{f['_id']}")])
    buttons.append(pager("s:pg", page, total, PAGE))
    return text, kb(*buttons)


async def do_search(client, message, query: str):
    user = message.from_user
    doc = await users.get(user.id) or {}
    lang = doc.get("lang", "en")
    if not await settings.get("search_enabled"):
        await message.reply_text(t(lang, "search_off"))
        return
    if not await guards.fsub_gate(client, message, user, lang=lang):
        return
    query = query.strip()[:80]
    rows, total = await files.search(query, 0, PAGE)
    if not rows:
        await message.reply_text(t(lang, "search_none", q=esc(query)))
        return
    LAST_QUERY[user.id] = query
    if len(LAST_QUERY) > 5000:
        LAST_QUERY.pop(next(iter(LAST_QUERY)))
    text, markup = build_results(lang, query, rows, total, 0)
    await message.reply_text(text, reply_markup=markup)


@router.cb("s:pg")
async def search_page(client, cq, args):
    uid = cq.from_user.id
    doc = await users.get(uid) or {}
    lang = doc.get("lang", "en")
    query = LAST_QUERY.get(uid)
    if not query:
        return ("Search expired, send the name again.", True)
    page = max(0, int(args[0])) if args and args[0].isdigit() else 0
    rows, total = await files.search(query, page * PAGE, PAGE)
    if not rows:
        return ("No more results.", False)
    text, markup = build_results(lang, query, rows, total, page)
    await tg.show(cq, text, markup)
