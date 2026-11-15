"""Caption building: pure functions (no Telegram dependency), fully unit-testable."""
import html
import re
from html.parser import HTMLParser
from pathlib import PurePath
from urllib.parse import urlparse

LINK_KEYS = ("main_channel", "backup_channel", "movie_bot", "discussion_group")
LINK_LABELS = {"main_channel": "Main Channel", "backup_channel": "Backup Channel",
               "movie_bot": "Movie Bot", "discussion_group": "Discussion Group"}
PLACEHOLDERS = {"original_caption", *LINK_KEYS}
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre",
                "blockquote", "tg-spoiler"}
CAPTION_LIMIT = 1024
_PH = re.compile(r"\{(\w+)\}")

DEFAULT_TEMPLATE = (
    "🎬 {original_caption}\n\n"
    '💎 Main Channel: <a href="{main_channel}">Join Now</a>\n'
    '📢 Backup Channel: <a href="{backup_channel}">Join Now</a>\n'
    '🤖 Movie Bot: <a href="{movie_bot}">Start Bot</a>\n'
    '💬 Discussion Group: <a href="{discussion_group}">Join Group</a>'
)
MINIMAL_TEMPLATE = (
    "{original_caption}\n\n"
    '<a href="{main_channel}">Main Channel</a> | <a href="{backup_channel}">Backup</a>'
)


def u16len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")


def strip_tags(h: str) -> str:
    p = _Strip()
    p.feed(h or "")
    p.close()
    return "".join(p.parts)


def visible_len(h: str) -> int:
    return u16len(strip_tags(h))


class _TagCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.error: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.error = f"unsupported tag <{tag}>"
        elif tag == "a" and not any(k == "href" and v for k, v in attrs):
            self.error = "<a> needs an href"
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.error = self.error or f"unbalanced </{tag}>"
        else:
            self.stack.pop()


def validate_url(url: str) -> bool:
    url = (url or "").strip()
    if not url or len(url) > 300 or re.search(r"[\s\"'<>]", url):
        return False
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc) and "." in p.netloc


def validate_template(text: str) -> tuple[bool, str]:
    text = (text or "").strip()
    if not text:
        return False, "Template is empty."
    if "{original_caption}" not in text:
        return False, "Template must contain {original_caption} so the original caption is preserved."
    bad = sorted(set(_PH.findall(text)) - PLACEHOLDERS)
    if bad:
        return False, "Unknown placeholder(s): " + ", ".join("{%s}" % b for b in bad)
    chk = _TagCheck()
    try:
        chk.feed(text)
        chk.close()
    except Exception as e:  # malformed markup
        return False, f"HTML error: {e}"
    if chk.error or chk.stack:
        return False, chk.error or f"unclosed <{chk.stack[-1]}>"
    sample = {k: "https://t.me/example" for k in LINK_KEYS}
    if visible_len(render(text, "", sample)) > 500:
        return False, "Template text is too long (max ~500 visible characters)."
    return True, ""


def _norm_url(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower())
    return u.rstrip("/")


def _variants(url: str) -> list[str]:
    n = _norm_url(url)
    out = [n] if n else []
    m = re.match(r"t\.me/([a-z0-9_]{4,})(?:/|$)", n)
    if m:
        out.append("@" + m.group(1))
    return out


def remove_known_links(original_html: str, known_urls) -> str:
    """Drop every line that contains one of the known (current or old) links."""
    pats = []
    for u in known_urls:
        for v in _variants(u):
            pats.append(re.compile(r"(?<![\w@])" + re.escape(v) + r"(?![\w])"))
    if not pats:
        return (original_html or "").strip()
    kept = [ln for ln in (original_html or "").split("\n")
            if not any(p.search(ln.lower()) for p in pats)]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return text


def render(template: str, original_html: str, links: dict) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in template.split("\n"):
        keys = [k for k in _PH.findall(line) if k in LINK_KEYS]
        has_orig = "{original_caption}" in line
        valid = {k: (links.get(k) or "").strip() for k in keys}
        if not has_orig:
            if any(not validate_url(v) or _norm_url(v) in seen for v in valid.values()):
                continue                                   # unset / invalid / duplicate link -> drop line
            seen.update(_norm_url(v) for v in valid.values())
        for k in keys:
            v = valid[k] if validate_url(valid[k]) else ""
            line = line.replace("{%s}" % k, html.escape(v, quote=True))
        out.append(line)
    text = "\n".join(out).replace("{original_caption}", original_html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _truncate_u16(s: str, n: int) -> str:
    while s and u16len(s) > n:
        s = s[:-1]
    return s


def fallback_title(file_name: str | None) -> str:
    if file_name:
        stem = PurePath(file_name).stem.replace("_", " ").strip()
        if stem:
            return stem
    return "New File"


def _strip_prefix(cleaned: str, template: str) -> str:
    prefix = template.split("{original_caption}")[0]
    if "{" in prefix:
        return cleaned
    s = cleaned.lstrip()
    for cand in (prefix.strip(), strip_tags(prefix).strip()):
        if cand and s.startswith(cand):
            return s[len(cand):].lstrip(" ")
    return cleaned


def build_caption(original_html: str | None, template: str, links: dict, old_links=(),
                  file_name: str | None = None, limit: int = CAPTION_LIMIT) -> str:
    known = [v for v in links.values() if v] + list(old_links or [])
    cleaned = remove_known_links(original_html or "", known)
    cleaned = _strip_prefix(cleaned, template)
    if not strip_tags(cleaned).strip():
        cleaned = html.escape(fallback_title(file_name))
    out = render(template, cleaned, links)
    if visible_len(out) <= limit:
        return out
    room = limit - visible_len(render(template, "", links))
    plain = html.unescape(strip_tags(cleaned)).strip()
    if room >= 10:
        short = html.escape(_truncate_u16(plain, room - 1)) + "…"
        out = render(template, short, links)
        if visible_len(out) <= limit:
            return out
    return html.escape(_truncate_u16(plain, limit - 1)) + "…"
