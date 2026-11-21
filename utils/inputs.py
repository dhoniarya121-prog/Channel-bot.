"""Parsing of what the owner types into the bot menu (pure functions, unit-testable)."""
import re

from utils.buttons import MAX_TEXT, parse_post_link
from utils.captions import make_key, normalize_url, validate_url


def parse_link_line(text: str) -> tuple[str | None, str | None, str | None]:
    """`Name | https://t.me/x` (or `Name https://t.me/x`) -> (key, url, error)."""
    text = (text or "").strip()
    name, sep, url = text.partition("|")
    if not sep:
        name, _, url = text.partition(" ")
    key = make_key(name)
    url = normalize_url(url)
    if not key:
        return None, None, "Link name must have letters/numbers (e.g. backup, main_channel)."
    if not validate_url(url):
        return None, None, "Link must look like https://t.me/yourchannel (or @yourchannel)."
    return key, url, None


def parse_old_links(text: str) -> list[str]:
    """Any number of links / @handles separated by spaces or new lines."""
    out = []
    for tok in re.split(r"[\s,]+", (text or "").strip()):
        tok = tok.strip()
        if re.fullmatch(r"@[A-Za-z0-9_]{4,}", tok) or validate_url(normalize_url(tok)):
            out.append(tok if tok.startswith("@") else normalize_url(tok))
    return out


def parse_channel_ref(text: str):
    """Channel id / @username / t.me link / post link -> int | '@name' | None."""
    t = (text or "").strip()
    if re.fullmatch(r"-?\d{5,}", t):
        n = int(t)
        return n if n < 0 else int("-100" + t)
    ref = parse_post_link(t)
    if ref:
        return ref[0]
    m = re.fullmatch(r"@([A-Za-z][A-Za-z0-9_]{3,31})", t) or \
        re.fullmatch(r"(?:https?://)?(?:www\.)?t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?(?:\?.*)?", t)
    return "@" + m.group(1) if m else None


def parse_button_text(text: str) -> tuple[str | None, str | None]:
    t = (text or "").strip()
    if not t:
        return None, "Send the text that should appear on the button."
    if len(t) > MAX_TEXT:
        return None, f"Too long ({len(t)}). Maximum {MAX_TEXT} characters."
    return t, None
