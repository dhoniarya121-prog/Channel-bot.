"""Test helpers. If pymongo/motor are missing, tiny stand-ins are installed so the suite still runs;
set TEST_MONGO_URI (and install motor) to run the very same tests against a real MongoDB."""
import os
import sys
import types
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pymongo  # noqa: F401
except ImportError:
    pm = types.ModuleType("pymongo")
    errs = types.ModuleType("pymongo.errors")

    class DuplicateKeyError(Exception):
        pass

    errs.DuplicateKeyError = DuplicateKeyError
    pm.errors = errs
    sys.modules["pymongo"] = pm
    sys.modules["pymongo.errors"] = errs

os.environ.setdefault("OWNER_ID", "1")
import config  # noqa: E402

config.OWNER_IDS = {1}

from database import admins, mongo, settings  # noqa: E402
from tests.fake_mongo import FakeDB  # noqa: E402

USING_REAL_MONGO = False


async def make_db():
    """Returns (db, cleanup)."""
    global USING_REAL_MONGO
    uri = os.getenv("TEST_MONGO_URI")
    if uri:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(uri, tz_aware=True)
        name = "roaroic_test_" + uuid.uuid4().hex[:8]
        USING_REAL_MONGO = True
        mongo.use(client[name])

        async def cleanup():
            await client.drop_database(name)
            client.close()
        return client[name], cleanup
    db = FakeDB()
    mongo.use(db)
    async def cleanup():
        return None
    return db, cleanup


async def fresh():
    db, cleanup = await make_db()
    settings.clear_cache()
    admins.invalidate()
    await mongo.ensure_indexes()
    return db, cleanup


def install_stubs():
    """Used only by the smoke test when pyrogram/aiohttp are not installed."""
    from unittest.mock import MagicMock
    try:
        import pyrogram  # noqa: F401
    except ImportError:
        mod = MagicMock(name="pyrogram")
        types_mod = types.ModuleType("pyrogram.types")

        class InlineKeyboardButton:
            def __init__(self, text, callback_data=None, url=None, **kw):
                self.text, self.callback_data, self.url = text, callback_data, url

        class InlineKeyboardMarkup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        class CallbackQuery:
            pass
        types_mod.InlineKeyboardButton, types_mod.InlineKeyboardMarkup = InlineKeyboardButton, InlineKeyboardMarkup
        types_mod.CallbackQuery = CallbackQuery
        mod.types = types_mod
        sys.modules.update({"pyrogram": mod, "pyrogram.types": types_mod,
                            "pyrogram.errors": MagicMock(name="pyrogram.errors"),
                            "pyrogram.enums": MagicMock(name="pyrogram.enums")})
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        sys.modules["aiohttp"] = MagicMock(name="aiohttp")
