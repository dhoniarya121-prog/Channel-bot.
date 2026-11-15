"""Static/structural checks of the Telegram layer. They do NOT talk to Telegram.
If pyrogram is not installed, a small stand-in is used so modules can still be imported."""
import asyncio
import glob
import importlib
import os
import re
import unittest

from tests import helpers

helpers.install_stubs()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "plugins", "*.py"))
                 if not p.endswith("__init__.py"))


class TestTelegramLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mods = {n: importlib.import_module(f"plugins.{n}") for n in PLUGINS}
        from utils import router
        cls.router = router

    def test_all_plugins_import_without_missing_imports(self):
        self.assertGreaterEqual(len(self.mods), 14)

    def test_registered_handlers_are_coroutines_and_perms_valid(self):
        from database import admins
        valid = set(admins.PERMS) | {"admin", "owner", None}
        for prefix, (fn, perm) in self.router._CB.items():
            self.assertTrue(asyncio.iscoroutinefunction(fn), prefix)
            self.assertIn(perm, valid, prefix)
        for action, (fn, perm) in self.router._IN.items():
            self.assertTrue(asyncio.iscoroutinefunction(fn), action)
            self.assertIn(perm, valid, action)
        self.assertGreater(len(self.router._CB), 100)

    def _sources(self):
        for sub in ("plugins", "keyboards", "utils"):
            for p in glob.glob(os.path.join(ROOT, sub, "*.py")):
                with open(p, encoding="utf-8") as fh:
                    yield p, fh.read()

    def test_every_callback_literal_has_a_handler(self):
        ns = {p.split(":")[0] for p in self.router.cb_prefixes()}
        pat = re.compile(r"""(?<![\w:])f?["']((?:%s):[^"']*)["']""" % "|".join(sorted(ns)))
        checked, bad = 0, []
        for path, src in self._sources():
            if path.endswith("router.py"):
                continue
            for lit in pat.findall(src):
                data = lit.split("{")[0].rstrip(":")
                checked += 1
                if not self.router.resolve_cb(data):
                    bad.append((os.path.basename(path), lit))
        self.assertGreater(checked, 150)
        self.assertEqual(bad, [], f"callbacks without a handler: {bad}")

    def test_every_input_action_has_a_handler(self):
        pat = re.compile(r"""(?:ask\(cq, |set_state\([^,()]+(?:\.\w+)*, |number_prompt\(cq, )f?["'](\w+)["']""")
        used = set()
        for _, src in self._sources():
            used |= set(pat.findall(src))
        self.assertGreater(len(used), 20)
        self.assertEqual(sorted(a for a in used if not self.router.get_input(a)), [])

    def test_translations_complete(self):
        from utils.i18n import S
        self.assertEqual(set(S["en"]), set(S["hi"]))
        keys = set()
        for _, src in self._sources():
            keys |= set(re.findall(r"\bt\([^,()]+(?:\([^)]*\))?[^,()]*, \"(\w+)\"", src))
        from plugins.sharing import SHARE_REASONS
        from utils.delivery import REASON_KEYS
        keys |= set(SHARE_REASONS.values()) | set(REASON_KEYS.values())
        self.assertEqual(sorted(k for k in keys if k not in S["en"] and not k.startswith("status_")), [])

    def test_keyboards_respect_telegram_callback_limit(self):
        from keyboards import user as ku
        from plugins import admin, filters
        token, uid = "AbCdEfGhIjKl", 123456789012
        markups = [ku.main_menu("en", False, True), ku.lang_kb(), ku.get_link_kb("en", token),
                   ku.fsub_kb("en", [{"chat_id": -1001234567890, "title": "T", "username": "x"}], "f_" + token),
                   filters.build_results("en", "q", [{"_id": token, "file_name": "a.mkv"}], 20, 0)[1],
                   admin.main_menu_kb(),
                   admin.user_card({"_id": uid, "first_name": "A", "perms": {}})[1]]
        n = 0
        for m in markups:
            for row in m.inline_keyboard:
                for b in row:
                    if b.callback_data is not None:
                        n += 1
                        self.assertLessEqual(len(b.callback_data.encode()), 64, b.callback_data)
                        self.assertTrue(self.router.resolve_cb(b.callback_data), b.callback_data)
        self.assertGreater(n, 40)

    def test_main_admin_menu_covers_every_requested_section(self):
        from plugins import admin
        labels = " ".join(b.text for r in admin.main_menu_kb().inline_keyboard for b in r)
        for name in ["Dashboard", "User Management", "File Management", "Sharing Management", "Premium Management",
                     "Referral Management", "Caption Settings", "Channel Settings", "Force Subscribe", "Broadcast",
                     "Statistics", "Admin Permissions", "Security Settings", "Maintenance Mode", "Database Backup",
                     "Bot Logs", "Restart / Status"]:
            self.assertIn(name, labels)

    def test_forbidden_features_are_absent(self):
        banned = re.compile(r"expire_at|expires_at|one_time|one-time|download_count|downloads|download counter|"
                            r"file_expiry|custom_expiry", re.I)
        for path, src in self._sources():
            if path.endswith("test_smoke.py"):
                continue
            self.assertIsNone(banned.search(src), f"{path}: {banned.search(src)}")


if __name__ == "__main__":
    unittest.main()
