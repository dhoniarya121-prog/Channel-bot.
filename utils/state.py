"""Short-lived per-admin/user 'waiting for input' state (in memory, TTL based)."""
import time

TTL = 300
_STATE: dict[int, tuple[float, str, dict]] = {}
_NEW: dict[int, float] = {}


def set_state(uid: int, action: str, **ctx) -> None:
    _STATE[uid] = (time.monotonic() + TTL, action, ctx)


def pop_state(uid: int):
    item = _STATE.pop(uid, None)
    if not item or item[0] < time.monotonic():
        return None
    return item[1], item[2]


def peek_state(uid: int):
    item = _STATE.get(uid)
    return (item[1], item[2]) if item and item[0] >= time.monotonic() else None


def clear_state(uid: int) -> None:
    _STATE.pop(uid, None)


def mark_new(uid: int) -> None:
    _NEW[uid] = time.monotonic() + 120


def pop_new(uid: int) -> bool:
    return _NEW.pop(uid, 0) >= time.monotonic()
