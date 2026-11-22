"""Caption building: pure functions (no Telegram dependency), fully unit-testable.

Template placeholders: {original_caption}, {<link>} = URL, {<link>_at} = @username text (clickable in Telegram)
where <link> is any configured link name (defaults: main_channel, backup_channel, movie_bot, discussion_group)."""
import html
import re
from html.parser import HTMLParser
from pathlib import PurePath
from urllib.parse import urlparse

DEFAULT_LINK_KEYS = ("main_channel", "backup_channel", "movie_bot", "discussion_group")
LINK_KEYS = DEFAULT_LINK_KEYS            # backwards compatible alias
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre",
                "blockquote", "tg-spoiler"}
CAPTION_LIMIT = 1024
_PH = re.compile(r"\{(\w+)\}")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,19}$")
NUMS = "❶❷❸❹❺❻❼❽❾❿"
PROMO_WORDS = {"join", "backup", "channel", "main", "premium", "adult", "bot", "group", "follow", "subscribe",
               "link", "share", "support", "now", "movie", "movies", "updates", "official", "telegram", "click",
               "here", "via", "by", "for", "more", "visit", "download", "from", "our", "my", "the", "see",
               "check", "get", "contact", "and", "at", "on", "to", "us"}

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


DIVIDER = "★━━━━━━❘༻༺❘━━━━━━★"
ROAROIC_LINKS = {
    "main_channel": "https://t.me/roaroic1",
    "movie_bot": "https://t.me/roaroic_bot",
    "movies_group": "https://t.me/roaroicgroup",
    "discussion_group": "https://t.me/+HwZPzMx1njs2N2Y9",
    "notification_channel": "https://t.me/+vNAhFBYrIQg5ZTk9",
    "backup_channel": "https://t.me/roaroic0",
}
ROAROIC_SIMPLE_TEMPLATE = (
    "<b>[ {backup_channel_at} ]</b> {original_caption}\n\n"
    "<blockquote>✦━━━━━ 🔥 𝗝𝗢𝗜𝗡 𝗢𝗨𝗥 𝗡𝗘𝗧𝗪𝗢𝗥𝗞 🔥 ━━━━━✦\n"
    '🎬 ➤ <b><a href="{main_channel}">𝗠𝗢𝗩𝗜𝗘 𝗨𝗣𝗗𝗔𝗧𝗘𝗦</a></b>\n'
    '🤖 ➤ <b><a href="{movie_bot}">𝗠𝗢𝗩𝗜𝗘 𝗕𝗢𝗧</a></b>\n'
    '👥 ➤ <b><a href="{movies_group}">𝗠𝗢𝗩𝗜𝗘𝗦 𝗚𝗥𝗢𝗨𝗣</a></b>\n'
    '💬 ➤ <b><a href="{discussion_group}">𝗗𝗜𝗦𝗖𝗨𝗦𝗦𝗜𝗢𝗡 𝗚𝗥𝗢𝗨𝗣</a></b>\n'
    '🔔 ➤ <b><a href="{notification_channel}">𝗡𝗢𝗧𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟</a></b>\n'
    '💾 ➤ <b><a href="{backup_channel}">𝗕𝗔𝗖𝗞𝗨𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟</a></b>\n'
    "✦━━━━━━━━━━━━━━━━━━━━━━✦</blockquote>\n"
    + DIVIDER + "\n"
    "⚡ <b>ROAROIC MOVIE'S || 0.1</b> ⚡"
)
ROAROIC_TEMPLATE = (
    "<b>[ {backup_channel_at} ]</b> {original_caption}\n\n"
    + DIVIDER + "\n"
    "<blockquote>✨ <b>𝗝𝗢𝗜𝗡 𝗢𝗨𝗥 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦</b>\n"
    '🎬 ❯❯ <b><a href="{main_channel}">𝗠𝗢𝗩𝗜𝗘 𝗨𝗣𝗗𝗔𝗧𝗘𝗦</a></b>\n'
    '💾 ❯❯ <b><a href="{backup_channel}">𝗕𝗔𝗖𝗞𝗨𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟</a></b>\n'
    '🔔 ❯❯ <b><a href="{notification_channel}">𝗡𝗢𝗧𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟</a></b>\n'
    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈</blockquote>\n"
    "<blockquote>🍿 <b>𝗪𝗔𝗧𝗖𝗛 • 𝗖𝗛𝗔𝗧 • 𝗥𝗘𝗤𝗨𝗘𝗦𝗧</b>\n"
    '🤖 ❯❯ <b><a href="{movie_bot}">𝗠𝗢𝗩𝗜𝗘 𝗕𝗢𝗧</a></b>\n'
    '👥 ❯❯ <b><a href="{movies_group}">𝗠𝗢𝗩𝗜𝗘𝗦 𝗚𝗥𝗢𝗨𝗣</a></b>\n'
    '💬 ❯❯ <b><a href="{discussion_group}">𝗗𝗜𝗦𝗖𝗨𝗦𝗦𝗜𝗢𝗡 𝗚𝗥𝗢𝗨𝗣</a></b>\n'
    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈</blockquote>\n"
    + DIVIDER + "\n"
    "💫 <b>ROAROIC MOVIE'S || 0.1</b> 💫"
)


def label(key: str) -> str:
    return key.replace("_", " ").upper()


def build_quote_template(keys) -> str:
    """Quote-block style: original caption, then a blockquote with numbered `NAME ➡ @username` lines."""
    lines = ["{original_caption}", "", "<blockquote>★───────|꧁꧂|───────★"]
    for i, k in enumerate(list(keys)[:10]):
        lines.append("%s %s ➡ {%s_at}" % (NUMS[i], label(k), k))
    lines.append("</blockquote>")
    return "\n".join(lines)


QUOTE_TEMPLATE = build_quote_template(DEFAULT_LINK_KEYS)


def make_key(name: str) -> str | None:
    k = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:20].strip("_")
    if not k:
        return None
    if not k[0].isalpha():
        k = "l_" + k[:17]
    if k.endswith("_at") or k == "original_caption" or not KEY_RE.match(k):
        return None
    return k


def handle_of(url: str) -> str:
    m = re.match(r"^(?:https?://)?(?:www\.)?t\.me/([A-Za-z0-9_]{4,})(?:/|\?|$)", (url or "").strip())
    if m and m.group(1).lower() not in ("joinchat", "c", "addlist"):
        return "@" + m.group(1)
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip())


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


def autoclose(h: str) -> str:
    """Close any tag left open (e.g. after a template line was dropped) so Telegram accepts the markup."""
    stack = []
    for m in re.finditer(r"<(/?)([a-zA-Z-]+)[^>]*>", h):
        if m.group(1):
            if stack and stack[-1] == m.group(2).lower():
                stack.pop()
        else:
            stack.append(m.group(2).lower())
    return h + "".join(f"</{t}>" for t in reversed(stack))


def normalize_url(s: str) -> str:
    """Friendly input: `@name` -> https://t.me/name, `t.me/name` -> https://t.me/name. Anything else unchanged."""
    s = (s or "").strip()
    m = re.fullmatch(r"@([A-Za-z][A-Za-z0-9_]{3,31})", s)
    if m:
        return "https://t.me/" + m.group(1)
    if re.match(r"^(?:www\.)?(?:t|telegram)\.me/", s, re.I):
        return "https://" + re.sub(r"^www\.", "", s, flags=re.I)
    return s


def validate_url(url: str) -> bool:
    url = (url or "").strip()
    if not url or len(url) > 300 or re.search(r"[\s\"'<>]", url):
        return False
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc) and "." in p.netloc


def validate_template(text: str, keys=DEFAULT_LINK_KEYS) -> tuple[bool, str]:
    text = (text or "").strip()
    if not text:
        return False, "Template is empty."
    if "{original_caption}" not in text:
        return False, "Template must contain {original_caption} so the original caption is preserved."
    allowed = {"original_caption", *keys, *(k + "_at" for k in keys)}
    bad = sorted(set(_PH.findall(text)) - allowed)
    if bad:
        return False, "Unknown placeholder(s): " + ", ".join("{%s}" % b for b in bad)
    chk = _TagCheck()
    try:
        chk.feed(text)
        chk.close()
    except Exception as e:
        return False, f"HTML error: {e}"
    if chk.error or chk.stack:
        return False, chk.error or f"unclosed <{chk.stack[-1]}>"
    sample = {k: "https://t.me/example" + str(i) * 2 for i, k in enumerate(keys)}
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


_ANCHOR = re.compile(r"<a\s[^>]*href=\"([^\"]*)\"[^>]*>.*?</a>", re.I | re.S)
_TAGS = re.compile(r"(<[^>]+>)")


def _strip_line(line: str, pats) -> str | None:
    """Remove known links from one line. Returns the cleaned line, or None when nothing useful is left."""
    changed = False

    def drop_anchor(m):
        nonlocal changed
        if any(p.search(_norm_url(html.unescape(m.group(1)))) for p in pats):
            changed = True
            return ""
        return m.group(0)
    line = _ANCHOR.sub(drop_anchor, line)
    parts = []
    for seg in _TAGS.split(line):
        if seg.startswith("<"):
            parts.append(seg)
            continue
        for p in pats:
            seg, n = p.subn("", seg)
            changed = changed or n > 0
        seg = re.sub(r"https?://(?=\s|$)", "", seg)       # scheme left behind by a removed t.me link
        parts.append(seg)
    if not changed:
        return line
    rest = "".join(parts)
    rest = re.sub(r"[\(\[\{]\s*[\)\]\}]", "", rest)
    rest = re.sub(r"[ \t]{2,}", " ", rest).strip(" \t-–—|•:➡➜→>·")
    words = re.findall(r"[^\W_]+", strip_tags(rest))
    if any(w.lower() not in PROMO_WORDS and not w.isdigit() for w in words):
        return rest
    return None


def remove_known_links(original_html: str, known_urls) -> str:
    """Strip every current/old promotional link. Lines that were only promotion disappear; a line that also
    carries real text (e.g. a title with an @handle) keeps that text."""
    pats = [re.compile(r"(?<![\w@])" + re.escape(v) + r"(?![\w])", re.I)
            for u in known_urls for v in _variants(u)]
    if not pats:
        return (original_html or "").strip()
    kept = [r for r in (_strip_line(ln, pats) for ln in (original_html or "").split("\n")) if r is not None]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _resolve(ph: str, links: dict):
    if ph in links:
        return "url", ph
    if ph.endswith("_at") and ph[:-3] in links:
        return "at", ph[:-3]
    return None


def render(template: str, original_html: str, links: dict) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in template.split("\n"):
        phs = [p for p in _PH.findall(line)]
        has_orig = "original_caption" in phs
        refs = [_resolve(p, links) for p in phs if p != "original_caption"]
        if not has_orig:
            if any(r is None for r in refs):
                continue                                    # unknown placeholder -> drop line
            urls = [(links.get(k) or "").strip() for _, k in refs]
            if any(not validate_url(u) or _norm_url(u) in seen for u in urls):
                continue                                    # unset / invalid / duplicate link -> drop line
            seen.update(_norm_url(u) for u in urls)
        for p in set(phs):
            if p == "original_caption":
                continue
            r = _resolve(p, links)
            val = ""
            if r:
                u = (links.get(r[1]) or "").strip()
                if validate_url(u):
                    val = html.escape(u if r[0] == "url" else handle_of(u), quote=True)
            line = line.replace("{%s}" % p, val)
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


_WRAP = r"(?:<(?:b|i|u|s|em|strong|ins|del|strike|code|blockquote|tg-spoiler)>)+"


def _wrapper_tags(template: str) -> list[str]:
    """Tags a template puts right around {original_caption}, outermost first (e.g. ['blockquote', 'b'])."""
    pre = template.split("{original_caption}")[0]
    m = re.search("(" + _WRAP + r")\s*$", pre)
    return re.findall(r"<([a-z-]+)>", m.group(1)) if m else []


def _unwrap(cleaned: str, tags: list[str]) -> str:
    """Remove those wrapper tags from an already-edited caption so they are not added twice."""
    if not tags:
        return cleaned
    s = cleaned.strip()
    opening = "".join(f"<{t}>" for t in tags)
    closing = "".join(f"</{t}>" for t in reversed(tags))
    if s.startswith(opening) and s.endswith(closing) and len(s) > len(opening) + len(closing):
        return s[len(opening):-len(closing)]
    return cleaned


def _strip_prefix(cleaned: str, template: str, links: dict | None = None) -> str:
    prefix = template.split("{original_caption}")[0]
    prefix = re.sub(_WRAP + r"\s*$", "", prefix)           # tags wrapped around the caption are handled by _unwrap
    if "{" in prefix and links:
        prefix = render(prefix, "", links)          # e.g. "[ @name ]" prefix built from a link placeholder
    if "{" in prefix:
        return cleaned
    s = cleaned.lstrip()
    last = prefix.rsplit("\n", 1)[-1]                     # earlier header lines are already removed by _drop_footer
    for cand in (prefix.strip(), strip_tags(prefix).strip(), last.strip(), strip_tags(last).strip()):
        if cand and s.startswith(cand):
            return s[len(cand):].lstrip(" ")
    return cleaned


def _drop_footer(h: str, footer_texts: set[str]) -> str:
    """Remove lines that are exactly our own previously-added footer, and lines holding only leftover tags."""
    kept = []
    for ln in (h or "").split("\n"):
        text = strip_tags(ln).strip()
        if text in footer_texts or (ln.strip() and not text):
            continue
        kept.append(ln)
    return "\n".join(kept)


def build_caption(original_html: str | None, template: str, links: dict, old_links=(),
                  file_name: str | None = None, limit: int = CAPTION_LIMIT) -> str:
    known = [v for v in links.values() if v] + list(old_links or [])
    footer = {strip_tags(ln).strip() for ln in render(template, "", links).split("\n")} - {""}
    cleaned = _unwrap(_strip_prefix(_drop_footer(original_html or "", footer), template, links),
                      _wrapper_tags(template))
    cleaned = remove_known_links(cleaned, known)
    if not strip_tags(cleaned).strip():
        cleaned = html.escape(fallback_title(file_name))
    out = autoclose(render(template, cleaned, links))
    if visible_len(out) <= limit:
        return out
    room = limit - visible_len(render(template, "", links))
    plain = html.unescape(strip_tags(cleaned)).strip()
    if room >= 10:
        short = html.escape(_truncate_u16(plain, room - 1)) + "…"
        out = autoclose(render(template, short, links))
        if visible_len(out) <= limit:
            return out
    return html.escape(_truncate_u16(plain, limit - 1)) + "…"
