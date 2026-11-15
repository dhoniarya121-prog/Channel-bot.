"""In-memory sliding-window rate limiter with strike based temporary mutes."""
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self):
        self._hits: dict = {}
        self._strikes: dict = {}
        self._muted: dict = {}
        self._notified: dict = {}

    def hit(self, key, limit: int, window: float, now: float | None = None) -> tuple[bool, float]:
        now = time.monotonic() if now is None else now
        dq = self._hits.setdefault(key, deque())
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False, max(0.0, window - (now - dq[0]))
        dq.append(now)
        return True, 0.0

    def strike(self, key, mute_after: int, mute_for: float, strike_window: float = 300,
               now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        dq = self._strikes.setdefault(key, deque())
        while dq and now - dq[0] > strike_window:
            dq.popleft()
        dq.append(now)
        if len(dq) >= mute_after:
            self._muted[key] = now + mute_for
            dq.clear()
            return True
        return False

    def muted_for(self, key, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        until = self._muted.get(key, 0)
        if until <= now:
            self._muted.pop(key, None)
            return 0.0
        return until - now

    def notify_due(self, key, gap: float, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if self._notified.get(key, -1e18) + gap <= now:
            self._notified[key] = now
            return True
        return False

    def prune(self, now: float | None = None, max_age: float = 900) -> None:
        now = time.monotonic() if now is None else now
        for store in (self._hits, self._strikes):
            for k in [k for k, dq in store.items() if not dq or now - dq[-1] > max_age]:
                store.pop(k, None)
        for k in [k for k, v in self._muted.items() if v <= now]:
            self._muted.pop(k, None)
        for k in [k for k, v in self._notified.items() if now - v > max_age]:
            self._notified.pop(k, None)


limiter = SlidingWindowLimiter()
