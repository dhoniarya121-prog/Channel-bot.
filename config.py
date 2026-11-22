"""Configuration from environment variables. Settings made from the bot menu live in one JSON file (DATA_FILE)."""
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
VERSION = "3.1.0"

API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_IDS = _ids(os.getenv("OWNER_ID") or os.getenv("OWNER_IDS"))
# Channels whose posts get the caption. Empty = every channel where the bot is admin.
SOURCE_CHANNELS = _ids(os.getenv("SOURCE_CHANNELS"))
# PUBLIC_MODE=true: every Telegram user can use the bot for their own channels. false: only OWNER_ID users.
PUBLIC_MODE = os.getenv("PUBLIC_MODE", "true").strip().lower() not in ("0", "false", "no", "off")
# How many channels one normal user may add (OWNER_ID users are unlimited).
MAX_CHANNELS_PER_USER = int(os.getenv("MAX_CHANNELS_PER_USER") or 10)
PORT = int(os.getenv("PORT") or 8080)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SESSION_NAME = os.getenv("SESSION_NAME", "roaroic_caption")
# One small JSON file holds every setting made from the bot menu (per-channel caption, links, buttons).
# On Render put it on a persistent disk (see render.yaml), otherwise a redeploy resets it.
DATA_FILE = os.getenv("DATA_FILE", "data/settings.json")


def missing_required() -> list[str]:
    need = {"API_ID": API_ID, "API_HASH": API_HASH, "BOT_TOKEN": BOT_TOKEN, "OWNER_ID": OWNER_IDS}
    return [k for k, v in need.items() if not v]
