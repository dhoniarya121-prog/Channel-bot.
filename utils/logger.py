"""Logging with secret redaction."""
import logging
import re

import config

_PATTERNS = [
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"), "<bot-token>"),
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


def setup():
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler()
    sh.setFormatter(RedactFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root.addHandler(sh)
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
