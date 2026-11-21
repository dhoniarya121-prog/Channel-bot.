"""Channel URL-button panels: parsing and layout (pure functions, no Telegram dependency)."""
import re

from utils.captions import normalize_url, validate_url

MAX_BUTTONS = 20
MAX_TEXT = 40
# Auto colour cycle: button #1 -> slot 1, ... button #6 -> slot 1 again.
# Telegram natively colours only 3 styles (blue/green/red); slots 4-5 use a coloured emoji prefix instead.
COLOR_CYCLE = [
    {"style": "primary", "prefix": ""},    # blue
    {"style": "success", "prefix": ""},    # green
    {"style": "danger", "prefix": ""},     # red
    {"style": None, "prefix": "🟡 "},      # yellow
    {"style": None, "prefix": "🟣 "},      # purple
    {"style": None, "prefix": "🟠 "},      # orange
    {"style": None, "prefix": "🟤 "},      # brown
    {"style": None, "prefix": "⚪ "},      # white
    {"style": None, "prefix": "⚫ "},      # black
]
_LINK = re.compile(r"^(?:https?://)?t\.me/(?:c/(\d+)|([A-Za-z0-9_]{4,}))/(\d+)(?:/\d+)?/?(?:\?.*)?$")


def parse_lines(text: str) -> tuple[list[dict], list[str]]:
    """Each line: `Button text | https://url`. Returns (valid buttons, error messages)."""
    ok, errors = [], []
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        label, sep, url = line.partition("|")
        label, url = label.strip(), normalize_url(url)
        if not sep or not label or not url:
            errors.append(f"Line {n}: use  Text | https://link")
        elif len(label) > MAX_TEXT:
            errors.append(f"Line {n}: text longer than {MAX_TEXT} characters")
        elif not validate_url(url):
            errors.append(f"Line {n}: invalid URL (must start with http:// or https://)")
        else:
            ok.append({"text": label, "url": url})
    return ok, errors


def merge(existing: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """Append `new`, skipping duplicate URLs and respecting MAX_BUTTONS. Returns (list, added, skipped)."""
    out, seen, added = list(existing), {b["url"].lower().rstrip("/") for b in existing}, 0
    for b in new:
        key = b["url"].lower().rstrip("/")
        if key in seen or len(out) >= MAX_BUTTONS:
            continue
        out.append(b)
        seen.add(key)
        added += 1
    return out, added, len(new) - added


def build_rows(buttons: list[dict], per_row: int = 1) -> list[list[dict]]:
    per_row = 2 if per_row == 2 else 1
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def color_for(index: int) -> dict:
    """Colour slot for the button at position `index` (0-based), cycling through 5 colours."""
    return COLOR_CYCLE[index % len(COLOR_CYCLE)]


def parse_post_link(text: str):
    """`https://t.me/c/123/45` -> (-100123, 45); `https://t.me/name/45` -> ('@name', 45); else None."""
    m = _LINK.match((text or "").strip())
    if not m:
        return None
    chat = int("-100" + m.group(1)) if m.group(1) else "@" + m.group(2)
    return chat, int(m.group(3))
