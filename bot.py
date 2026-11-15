"""ROAROIC AUTO LINK BOT - entry point.

Architecture: Pyrogram/MTProto (Kurigram fork) bot client + Motor (async MongoDB) + tiny aiohttp health server.
"""
import asyncio
import logging
import os
import sys

import config
from utils import lifecycle, logger

log = logging.getLogger("roaroic")


async def main() -> None:
    missing = config.missing_required()
    if missing:
        print("Missing required environment variables: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    logger.setup()

    from pyrogram import Client, enums, idle
    from database import mongo
    from utils import health, workers

    await mongo.connect(config.MONGO_URI, config.DB_NAME)
    logger.db_handler.start()
    runner = await health.start_web(config.PORT)

    app = Client(config.SESSION_NAME, api_id=config.API_ID, api_hash=config.API_HASH,
                 bot_token=config.BOT_TOKEN, in_memory=True, plugins=dict(root="plugins"),
                 parse_mode=enums.ParseMode.HTML)
    await app.start()
    me = await app.get_me()
    log.info("%s started as @%s", config.BOT_NAME, me.username)

    tasks = [asyncio.create_task(workers.premium_worker(app)),
             asyncio.create_task(workers.backup_worker(app)),
             asyncio.create_task(health.monitor(app))]
    for oid in config.OWNER_IDS:
        try:
            await app.send_message(oid, f"✅ <b>{config.BOT_NAME}</b> v{config.VERSION} started.")
        except Exception:
            pass

    try:
        await idle()                       # returns on SIGINT / SIGTERM (Render stop/redeploy, /restart)
    finally:
        log.info("Shutting down gracefully…")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await app.stop()
        await runner.cleanup()
        await logger.db_handler.stop()
        await mongo.close()
    if lifecycle.RESTART_REQUESTED:
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    asyncio.run(main())
