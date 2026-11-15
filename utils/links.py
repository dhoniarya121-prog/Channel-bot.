import re


def share_link(bot_username: str, token: str) -> str:
    return f"https://t.me/{bot_username}?start=f_{token}"


def referral_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=r_{code}"


_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{6,40}$")


def valid_token(s: str) -> bool:
    return bool(_TOKEN.match(s or ""))
