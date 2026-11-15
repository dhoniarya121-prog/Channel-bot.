"""Callback-data and text-input routers (one dispatcher each, many registrations)."""
from typing import Callable

_CB: dict[str, tuple[Callable, str | None]] = {}
_IN: dict[str, tuple[Callable, str | None]] = {}


def cb(prefix: str, perm: str | None = None):
    """Register a callback handler. perm: admin permission, 'owner', or None (any user)."""
    def deco(fn):
        if prefix in _CB:
            raise RuntimeError(f"duplicate callback prefix {prefix}")
        _CB[prefix] = (fn, perm)
        return fn
    return deco


def on_input(action: str, perm: str | None = None):
    def deco(fn):
        if action in _IN:
            raise RuntimeError(f"duplicate input action {action}")
        _IN[action] = (fn, perm)
        return fn
    return deco


def resolve_cb(data: str):
    """Longest-prefix match on ':' boundaries -> (fn, perm, args) or None."""
    parts = data.split(":")
    for n in range(len(parts), 0, -1):
        p = ":".join(parts[:n])
        if p in _CB:
            fn, perm = _CB[p]
            return fn, perm, parts[n:]
    return None


def get_input(action: str):
    return _IN.get(action)


def cb_prefixes() -> list[str]:
    return sorted(_CB)


def input_actions() -> list[str]:
    return sorted(_IN)
