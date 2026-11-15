"""Only one long-running admin job (old-post processing / button re-apply) at a time."""
_S = {"name": None, "stop": False}


def acquire(name: str) -> bool:
    if _S["name"]:
        return False
    _S.update(name=name, stop=False)
    return True


def release() -> None:
    _S.update(name=None, stop=False)


def busy() -> str | None:
    return _S["name"]


def request_stop() -> None:
    _S["stop"] = True


def should_stop() -> bool:
    return _S["stop"]
