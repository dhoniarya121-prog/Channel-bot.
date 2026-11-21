"""ROAROIC CAPTION BOT - entry point. Pyrogram (Kurigram) + tiny aiohttp health server. Settings in one JSON file."""
import asyncio
import logging
import sys

import config
from utils import logger, store

log = logging.getLogger("roaroic")


async def main() -> None:
    missing = config.missing_required()
    if missing:
        print("Missing required environment variables: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    logger.setup()
    store.init()

    from pyrogram import Client, enums, idle
    from utils import health

    runner = await health.start_web(config.PORT)
    app = Client(config.SESSION_NAME, api_id=config.API_ID, api_hash=config.API_HASH,
                 bot_token=config.BOT_TOKEN, in_memory=True, plugins=dict(root="plugins"),
                 parse_mode=enums.ParseMode.HTML)
    await app.start()
    me = await app.get_me()
    log.info("%s started as @%s", config.BOT_NAME, me.username)
    from utils import tg
    if tg.colors_supported():
        log.info("Coloured buttons: ON")
    else:
        log.warning("Coloured buttons: OFF - installed pyrogram/kurigram has no button 'style' support. "
                    "Run: pip install -U --force-reinstall kurigram")
    try:
        await idle()
    finally:
        log.info("Shutting down…")
        await app.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
