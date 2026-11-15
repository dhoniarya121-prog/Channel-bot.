"""Force-subscribe evaluation, independent of Pyrogram (checker is injected)."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

log = logging.getLogger(__name__)
Checker = Callable[[dict, int], Awaitable["bool | None"]]


@dataclass
class FsubResult:
    missing: list = field(default_factory=list)   # user is definitely not a member
    unknown: list = field(default_factory=list)   # bot could not verify (fail-open)

    @property
    def blocked(self) -> bool:
        return bool(self.missing)


async def evaluate(user_id: int, channels: list[dict], checker: Checker) -> FsubResult:
    res = FsubResult()
    if not channels:
        return res
    answers = await asyncio.gather(*(checker(ch, user_id) for ch in channels), return_exceptions=True)
    for ch, ans in zip(channels, answers):
        if isinstance(ans, Exception):
            log.warning("force-sub check failed for %s: %s", ch.get("chat_id"), type(ans).__name__)
            res.unknown.append(ch)
        elif ans is True:
            continue
        elif ans is False:
            res.missing.append(ch)
        else:
            res.unknown.append(ch)
    return res
