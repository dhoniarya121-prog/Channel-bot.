"""Minimal stand-in for pyrogram so the plugins can be imported and driven in tests (no network, no Telegram)."""
import sys
import types


class _F:
    def __getattr__(self, name):
        return _F()

    def __call__(self, *a, **k):
        return _F()

    def __and__(self, o):
        return _F()

    __or__ = __rand__ = __ror__ = __and__

    def __invert__(self):
        return _F()

    def create(self, fn, name=None):
        return _F()


class RPCError(Exception):
    pass


class FloodWait(RPCError):
    value = 1


class MessageNotModified(RPCError):
    pass


class ChatAdminRequired(RPCError):
    pass


class Btn:
    def __init__(self, text, url=None, callback_data=None):
        self.text, self.url, self.callback_data = text, url, callback_data


class Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class Client:
    handlers = []

    @classmethod
    def _reg(cls, kind):
        def deco(*a, **k):
            def wrap(fn):
                cls.handlers.append((kind, fn))
                return fn
            return wrap
        return deco


Client.on_message = Client._reg("message")
Client.on_callback_query = Client._reg("callback")


def install():
    if "pyrogram" in sys.modules and getattr(sys.modules["pyrogram"], "_fake", False):
        return
    m = types.ModuleType("pyrogram")
    m._fake = True
    m.Client, m.filters = Client, _F()
    m.enums = types.SimpleNamespace(ParseMode=types.SimpleNamespace(HTML="html"))
    m.idle = lambda: None
    errs = types.ModuleType("pyrogram.errors")
    errs.RPCError, errs.FloodWait, errs.MessageNotModified, errs.ChatAdminRequired = (
        RPCError, FloodWait, MessageNotModified, ChatAdminRequired)
    typ = types.ModuleType("pyrogram.types")
    typ.InlineKeyboardButton, typ.InlineKeyboardMarkup = Btn, Markup
    sys.modules.update({"pyrogram": m, "pyrogram.errors": errs, "pyrogram.types": typ})
