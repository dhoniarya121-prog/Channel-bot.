"""What the bot is waiting for from each owner (one pending text input per user, kept in memory)."""
_P: dict[int, dict] = {}


def put(uid: int, kind: str, **data) -> None:
    _P[uid] = {"kind": kind, **data}


def get(uid: int) -> dict | None:
    return _P.get(uid)


def clear(uid: int) -> None:
    _P.pop(uid, None)
