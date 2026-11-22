"""Per-channel settings in one small JSON file (no database).

Scopes: DEFAULT ("d") holds the settings every channel inherits; a channel id holds that channel's own
overrides. A channel field set to None means "use the default". Settings.py only seeds the very first default.
"""
import contextvars
import copy
import json
import logging
import os
import re

import config
import settings
from utils import templates
from utils.captions import validate_url

log = logging.getLogger(__name__)
DEFAULT = "d"
MEMORY = ":memory:"          # init(MEMORY) = keep everything in RAM (tests)
MAX_LINKS = 20
MAX_OLD_LINKS = 30
_s: dict = {"path": None, "data": None}
_user: contextvars.ContextVar = contextvars.ContextVar("roaroic_user", default=None)


def _fresh_default() -> dict:
    return {"caption": True, "buttons_on": True, "template": "roaroic", "custom_template": "",
            "links": dict(settings.LINKS), "old_links": list(settings.OLD_LINKS), "buttons": [], "per_row": 1}


def _fresh_channel(title: str = "") -> dict:
    return {"title": title or "", "owner": None, "caption": True, "buttons_on": True, "template": None, "custom_template": "",
            "links": None, "old_links": None, "buttons": [], "per_row": 1,
            "color": "auto", "font": "normal"}


def _normalise(data) -> dict:
    data = data if isinstance(data, dict) else {}
    d = _fresh_default()
    d.update({k: v for k, v in (data.get("default") or {}).items() if k in d})
    channels, users = {}, {}
    for k, c in (data.get("channels") or {}).items():
        if not re.fullmatch(r"-?\d+", str(k)) or not isinstance(c, dict):
            continue
        ch = _fresh_channel()
        ch.update({kk: vv for kk, vv in c.items() if kk in ch})
        if not isinstance(ch["owner"], int) or isinstance(ch["owner"], bool):
            ch["owner"] = None
        channels[str(int(k))] = ch
    for k, u in (data.get("users") or {}).items():
        if not re.fullmatch(r"\d+", str(k)) or not isinstance(u, dict):
            continue
        ud = _fresh_default()
        ud.update({kk: vv for kk, vv in (u.get("default") or {}).items() if kk in ud})
        users[str(int(k))] = {"name": str(u.get("name") or "")[:64], "default": ud}
    for c in [d, *channels.values(), *(u["default"] for u in users.values())]:
        if c.get("per_row") not in (0, 1, 2, 3):
            c["per_row"] = 1
        if c.get("color", "auto") not in ("auto", "primary", "success", "danger", "none"):
            c["color"] = "auto"
        if c.get("font", "normal") not in ("normal", "bold", "small", "mono"):
            c["font"] = "normal"
        if not isinstance(c.get("buttons"), list):
            c["buttons"] = []
        if c.get("links") is not None and not isinstance(c["links"], dict):
            c["links"] = None
        if c.get("old_links") is not None and not isinstance(c["old_links"], list):
            c["old_links"] = None
    for c in [d, *(u["default"] for u in users.values())]:
        if not isinstance(c["links"], dict):
            c["links"] = dict(settings.LINKS)
        if not isinstance(c["old_links"], list):
            c["old_links"] = []
    banned = sorted({int(x) for x in (data.get("banned") or []) if re.fullmatch(r"\d+", str(x))})
    return {"version": 2, "default": d, "channels": channels, "users": users, "banned": banned}


def _load(path) -> dict:
    data = None
    if path and path != MEMORY and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            log.exception("Settings file unreadable - starting fresh (old file kept as .corrupt)")
            try:
                os.replace(path, path + ".corrupt")
            except OSError:
                pass
    return _normalise(data)


def init(path: str | None = None) -> None:
    _s["path"] = path if path is not None else config.DATA_FILE
    _s["data"] = _load(_s["path"])


def _d() -> dict:
    if _s["data"] is None:
        init()
    return _s["data"]


def _save() -> None:
    p = _s["path"]
    if not p or p == MEMORY:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_d(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError:
        log.exception("Could not save settings to %s", p)


def key(scope) -> str:
    return DEFAULT if scope in (None, DEFAULT) else str(int(scope))


# ---- who is using the bot (set once per incoming update by the plugins) -------------------------------------
def set_user(uid) -> None:
    _user.set(int(uid) if uid else None)


def current_user() -> int | None:
    return _user.get()


def is_admin(uid) -> bool:
    return bool(uid) and int(uid) in config.OWNER_IDS


def _user_rec(uid) -> dict:
    users = _d()["users"]
    rec = users.get(str(int(uid)))
    if rec is None:                                   # new user: starts from a copy of the global default
        rec = users[str(int(uid))] = {"name": "", "default": copy.deepcopy(_d()["default"])}
        rec["default"]["buttons"], rec["default"]["per_row"] = [], 1
    return rec


def touch_user(uid, name: str = "") -> bool:
    """Remember a user (first time = True). Keeps the display name fresh."""
    new = str(int(uid)) not in _d()["users"]
    rec = _user_rec(uid)
    name = (name or "")[:64]
    if new or (name and rec["name"] != name):
        rec["name"] = name or rec["name"]
        _save()
    return new


def _base(scope=None) -> dict:
    """The default settings that apply to a scope: the user's own default, or the channel owner's default."""
    d = _d()
    k = key(scope)
    if k == DEFAULT:
        uid = current_user()
        return _user_rec(uid)["default"] if uid else d["default"]
    c = d["channels"].get(k)
    owner = c.get("owner") if c else None
    rec = d["users"].get(str(owner)) if owner else None
    return rec["default"] if rec else d["default"]


def get(scope) -> dict | None:
    k = key(scope)
    return _base(DEFAULT) if k == DEFAULT else _d()["channels"].get(k)


def owner_of(scope) -> int | None:
    c = get(scope) if key(scope) != DEFAULT else None
    return c.get("owner") if c else None


def can_manage(uid, scope) -> bool:
    if key(scope) == DEFAULT:
        return True
    c = _d()["channels"].get(key(scope))
    return c is not None and (is_admin(uid) or (c.get("owner") is not None and c["owner"] == int(uid)))


def my_channels(uid=None) -> list[tuple[str, dict]]:
    uid = uid if uid is not None else current_user()
    return [(k, c) for k, c in list_channels() if is_admin(uid) or (uid and c.get("owner") == int(uid))]


def count_owned(uid) -> int:
    return sum(1 for c in _d()["channels"].values() if c.get("owner") == int(uid))


# ---- access / bans ------------------------------------------------------------------------------------------
def is_banned(uid) -> bool:
    return int(uid) in _d()["banned"] and not is_admin(uid)


def user_allowed(uid) -> bool:
    return bool(uid) and not is_banned(uid) and (config.PUBLIC_MODE or is_admin(uid))


def ban(uid, on: bool = True) -> None:
    b = set(_d()["banned"])
    (b.add if on else b.discard)(int(uid))
    _d()["banned"] = sorted(b)
    _save()


def stats() -> dict:
    return {"users": len(_d()["users"]), "channels": len(_d()["channels"]), "banned": len(_d()["banned"])}


def list_channels() -> list[tuple[str, dict]]:
    return sorted(_d()["channels"].items(), key=lambda kv: ((kv[1].get("title") or "").lower(), kv[0]))


def ensure_channel(chat_id: int, title: str | None = None, owner: int | None = None) -> tuple[dict, bool]:
    k = str(int(chat_id))
    ch = _d()["channels"].get(k)
    if ch is not None:
        changed = False
        if title and ch.get("title") != title:
            ch["title"], changed = title, True
        if owner and ch.get("owner") is None:          # an unclaimed channel gets its owner
            ch["owner"], changed = int(owner), True
        if changed:
            _save()
        return ch, False
    ch = _d()["channels"][k] = _fresh_channel(title or "")
    if owner:
        ch["owner"] = int(owner)
        _user_rec(owner)
    _save()
    return ch, True


def delete_channel(chat_id) -> bool:
    ok = _d()["channels"].pop(key(chat_id), None) is not None
    if ok:
        _save()
    return ok


def update(scope, **fields) -> bool:
    c = get(scope)
    if c is None:
        return False
    c.update(fields)
    _save()
    return True


def effective(scope=None) -> dict:
    """Everything caption/button code needs for one chat, with defaults filled in."""
    d = _base(scope)
    c = None if key(scope) == DEFAULT else _d()["channels"].get(key(scope))
    own_links = c is not None and c["links"] is not None
    links = c["links"] if own_links else d["links"]
    old = c["old_links"] if c is not None and c["old_links"] is not None else d["old_links"]
    if c is not None and c["template"]:
        tkey, custom = c["template"], c["custom_template"]
    else:
        tkey, custom = d["template"], d["custom_template"]
    base = c if c is not None else d
    return {
        "caption": bool(base["caption"]), "buttons_on": bool(base["buttons_on"]),
        "template_key": tkey, "template": templates.resolve(tkey, custom, links),
        "links": dict(links), "old_links": list(old),
        "buttons": list(c["buttons"]) if c is not None else [], "per_row": c["per_row"] if c is not None else 1,
        "color": c.get("color", "auto") if c is not None else "auto", "font": c.get("font", "normal") if c is not None else "normal",
        "own_links": own_links, "own_template": bool(c is not None and c["template"]),
        "own_old_links": bool(c is not None and c["old_links"] is not None),
    }


# ---- links -----------------------------------------------------------------------------------------------
def _own_links(scope) -> dict | None:
    c = get(scope)
    if c is None:
        return None
    if c["links"] is None:                       # first edit of a channel: start from a copy of the default links
        c["links"] = copy.deepcopy(_base(scope)["links"])
    return c["links"]


def set_link(scope, name: str, url: str) -> str | None:
    """Add or change a link. Returns an error text, or None when saved."""
    if not validate_url(url):
        return "That is not a valid link (it must start with https://)."
    links = _own_links(scope)
    if links is None:
        return "Channel not found."
    if name not in links and len(links) >= MAX_LINKS:
        return f"Maximum {MAX_LINKS} links."
    links[name] = url
    _save()
    return None


def del_link(scope, name: str) -> bool:
    links = _own_links(scope)
    if links is None or name not in links:
        return False
    del links[name]
    _save()
    return True


def reset_links(scope) -> bool:
    c = get(scope)
    if c is None or key(scope) == DEFAULT:
        return False
    c["links"] = None
    _save()
    return True


# ---- old links (stripped from captions) ---------------------------------------------------------------
def add_old_links(scope, items: list[str]) -> int:
    c = get(scope)
    if c is None:
        return 0
    cur = list(c["old_links"] if c["old_links"] is not None else _base(scope)["old_links"])
    seen = {x.lower() for x in cur}
    added = 0
    for it in items:
        if it.lower() not in seen and len(cur) < MAX_OLD_LINKS:
            cur.append(it)
            seen.add(it.lower())
            added += 1
    c["old_links"] = cur
    _save()
    return added


def clear_old_links(scope) -> bool:
    c = get(scope)
    if c is None:
        return False
    c["old_links"] = [] if key(scope) == DEFAULT else None
    _save()
    return True


# ---- buttons ---------------------------------------------------------------------------------------------
def buttons(scope) -> list[dict]:
    c = get(scope)
    return list(c["buttons"]) if c else []


def set_buttons(scope, items: list[dict]) -> bool:
    return update(scope, buttons=[{"text": b["text"], "url": b["url"]} for b in items])


# ---- backup / restore ------------------------------------------------------------------------------------
def export_json() -> bytes:
    return json.dumps(_d(), ensure_ascii=False, indent=1).encode("utf-8")


def import_json(raw: bytes) -> tuple[bool, str]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return False, "That file is not valid JSON."
    if not isinstance(data, dict) or "channels" not in data or "default" not in data:
        return False, "That does not look like a settings backup."
    _s["data"] = _normalise(data)
    _save()
    return True, f"{len(_d()['channels'])} channel(s) restored."
