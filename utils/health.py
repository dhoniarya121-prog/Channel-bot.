"""Health endpoint (for Render) and background health monitor."""
import asyncio
import logging
import os
import time

from aiohttp import web

import config
from database import mongo
from utils.text import fmt_uptime

log = logging.getLogger(__name__)
START = time.time()
_last = {"update": time.time(), "db_failures": 0, "alerted": False}


def mark_update() -> None:
    _last["update"] = time.time()


async def snapshot() -> dict:
    try:
        db_ms = await asyncio.wait_for(mongo.ping(), 5)
        db_ok = True
    except Exception:
        db_ms, db_ok = None, False
    rss = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS"):
                    rss = int(line.split()[1]) // 1024
    except OSError:
        pass
    return {"ok": db_ok, "db_ok": db_ok, "db_ms": round(db_ms, 1) if db_ms else None,
            "uptime": fmt_uptime(time.time() - START), "idle_s": int(time.time() - _last["update"]),
            "memory_mb": rss, "version": config.VERSION}


async def start_web(port: int) -> web.AppRunner:
    async def health(_):
        snap = await snapshot()
        return web.json_response(snap, status=200 if snap["ok"] else 503)

    async def root(_):
        return web.Response(text=f"{config.BOT_NAME} is running")

    app = web.Application()
    app.add_routes([web.get("/", root), web.get("/health", health)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Health server listening on :%s", port)
    return runner


async def monitor(client, interval: int = 300) -> None:
    """Pings MongoDB periodically; alerts the owner once after 3 consecutive failures."""
    while True:
        await asyncio.sleep(interval)
        snap = await snapshot()
        if snap["db_ok"]:
            if _last["alerted"]:
                await _alert(client, "✅ Database connection recovered.")
            _last.update(db_failures=0, alerted=False)
            continue
        _last["db_failures"] += 1
        log.error("Health check: MongoDB unreachable (%s consecutive)", _last["db_failures"])
        if _last["db_failures"] >= 3 and not _last["alerted"]:
            _last["alerted"] = True
            await _alert(client, "🚨 MongoDB has been unreachable for 3 health checks.")


async def _alert(client, text: str) -> None:
    for oid in config.OWNER_IDS:
        try:
            await client.send_message(oid, text)
        except Exception:
            pass
