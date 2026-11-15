"""Background tasks: premium expiry/notices, automatic backups, limiter cleanup."""
import asyncio
import logging
import time

import config
from database import premium, settings, users
from utils import backup, tg
from utils.i18n import t
from utils.ratelimit import limiter
from utils.text import fmt_dt

log = logging.getLogger(__name__)


async def _lang(uid: int) -> str:
    return ((await users.get(uid)) or {}).get("lang", "en")


async def premium_worker(client, interval: int = 300):
    while True:
        try:
            for uid in await premium.expire_due():
                await tg.notify(client, uid, t(await _lang(uid), "prem_expired", dev=config.DEVELOPER))
            if await settings.get("premium_notify"):
                for uid, days, end in await premium.due_for_notice(await settings.get("notify_days") or [3, 1]):
                    await tg.notify(client, uid, t(await _lang(uid), "prem_expiring", days=days,
                                                   until=fmt_dt(end), dev=config.DEVELOPER))
            limiter.prune()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("premium worker failed")
        await asyncio.sleep(interval)


async def send_backup(client, chat_id: int, caption: str = "💾 Database backup") -> int:
    sent = 0
    for path, n in await backup.create_backup():
        try:
            await tg.safe(client.send_document, chat_id, path, caption=f"{caption}\nDocuments: {n}")
            sent += 1
        except Exception:
            log.exception("backup upload failed")
    return sent


async def backup_worker(client, every: int = 86400):
    last = time.time()
    while True:
        await asyncio.sleep(3600)
        try:
            if await settings.get("auto_backup") and time.time() - last >= every:
                for oid in config.OWNER_IDS:
                    await send_backup(client, oid, "💾 Automatic daily backup")
                last = time.time()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("backup worker failed")
