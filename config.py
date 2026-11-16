"""Configuration from environment variables only. No database is used by this bot."""
import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _ids(raw: str | None) -> set[int]:
    return {int(x) for x in re.split(r"[,\s]+", raw or "") if re.fullmatch(r"-?\d+", x)}


BOT_NAME = "ROAROIC CAPTION BOT"
VERSION = "2.0.0"

API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_IDS = _ids(os.getenv("OWNER_ID") or os.getenv("OWNER_IDS"))
# Channels whose posts get the caption. Empty = every channel where the bot is admin.
SOURCE_CHANNELS = _ids(os.getenv("SOURCE_CHANNELS"))
PORT = int(os.getenv("PORT") or 8080)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SESSION_NAME = os.getenv("SESSION_NAME", "roaroic_caption")


def missing_required() -> list[str]:
    need = {"API_ID": API_ID, "API_HASH": API_HASH, "BOT_TOKEN": BOT_TOKEN, "OWNER_ID": OWNER_IDS}
    return [k for k, v in need.items() if not v]
