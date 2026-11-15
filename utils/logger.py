"""Logging with secret redaction; WARNING+ records are also persisted to MongoDB (logs collection)."""
import asyncio
import logging
import re

import config

_PATTERNS = [
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"), "<bot-token>"),
    (re.compile(r"mongodb(?:\+srv)?://\S+", re.I), "<mongo-uri>"),
    (re.compile(r"(api_hash|api_id|token|password|secret)(\s*[=:]\s*)\S+", re.I), r"\1\2<redacted>"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "<hash>"),
]


def redact(s: str) -> str:
    for pat, rep in _PATTERNS:
        s = pat.sub(rep, s)
    return s


class RedactFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class DBLogHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue | None = None
        self.task: asyncio.Task | None = None

    def start(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue(maxsize=500)
        self.task = asyncio.create_task(self._writer())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def emit(self, record):
        if not self.loop or not self.queue:
            return
        try:
            item = (record.levelname, record.name, self.format(record))
            self.loop.call_soon_threadsafe(self._put, item)
        except Exception:
            pass

    def _put(self, item):
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def _writer(self):
        from database import logs
        while True:
            level, module, msg = await self.queue.get()
            try:
                await logs.write(level, module, msg)
            except Exception:       # never recurse into logging from the log writer
                pass


db_handler = DBLogHandler()


def setup():
    fmt = RedactFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    db_handler.setFormatter(fmt)
    root.addHandler(db_handler)
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
