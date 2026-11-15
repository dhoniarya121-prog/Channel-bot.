import html
import re
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def normalize_name(s: str | None) -> str:
    s = re.sub(r"[._\-+\[\]()]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def parse_int(s, lo: int | None = None, hi: int | None = None) -> int | None:
    try:
        v = int(str(s).strip())
    except (TypeError, ValueError):
        return None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        return None
    return v


def fmt_dt(dt: datetime | None) -> str:
    return as_aware(dt).strftime("%Y-%m-%d %H:%M UTC") if dt else "-"


def time_left(dt: datetime | None, now: datetime | None = None) -> str:
    if not dt:
        return "-"
    delta: timedelta = as_aware(dt) - (now or utcnow())
    if delta.total_seconds() <= 0:
        return "expired"
    d, rem = divmod(int(delta.total_seconds()), 86400)
    h, rem = divmod(rem, 3600)
    return f"{d}d {h}h" if d else f"{h}h {rem // 60}m"


def trunc(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_uptime(seconds: float) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    return f"{d}d {h}h {rem // 60}m"
