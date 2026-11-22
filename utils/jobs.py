"""Only one long-running job (old-post processing) at a time; remembers who started it."""
import config

_S = {"name": None, "stop": False, "owner": None}


def acquire(name: str, owner: int | None = None) -> bool:
    if _S["name"]:
        return False
    _S.update(name=name, stop=False, owner=owner)
    return True


def release() -> None:
    _S.update(name=None, stop=False, owner=None)


def busy() -> str | None:
    return _S["name"]


def owner() -> int | None:
    return _S["owner"]


def request_stop(uid: int | None = None) -> bool:
    """Stop the running job. A normal user may only stop their own job; OWNER_ID users may stop any."""
    if not _S["name"]:
        return True
    if uid is not None and _S["owner"] not in (None, uid) and uid not in config.OWNER_IDS:
        return False
    _S["stop"] = True
    return True


def should_stop() -> bool:
    return _S["stop"]
