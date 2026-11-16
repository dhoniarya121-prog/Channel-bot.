"""Tiny HTTP health endpoint (Render needs an open port)."""
import logging
import time

from aiohttp import web

import config
from utils.text import fmt_uptime

log = logging.getLogger(__name__)
START = time.time()


async def start_web(port: int) -> web.AppRunner:
    async def health(_):
        return web.json_response({"ok": True, "uptime": fmt_uptime(time.time() - START), "version": config.VERSION})

    async def root(_):
        return web.Response(text=f"{config.BOT_NAME} is running")

    app = web.Application()
    app.add_routes([web.get("/", root), web.get("/health", health)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Health server listening on :%s", port)
    return runner
