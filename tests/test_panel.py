import asyncio
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OWNER_ID", "1")

from tests import fake_pyrogram  # noqa: E402

fake_pyrogram.install()

from utils import inputs, jobs, pending, runner, store, templates, ui  # noqa: E402
from utils.captions import validate_template  # noqa: E402

CH = -1001234567890


def run(coro):
    return asyncio.run(coro)


class TestStore(unittest.TestCase):
    def setUp(self):
        store.init(store.MEMORY)

    def test_channel_inherits_default_until_changed(self):
        store.ensure_channel(CH, "Movies")
        e = store.effective(CH)
        self.assertFalse(e["own_links"])
        self.assertEqual(e["links"], store.effective(None)["links"])
        self.assertIsNone(store.set_link(CH, "site", "https://example.com/x"))
        e = store.effective(CH)
        self.assertTrue(e["own_links"])
        self.assertIn("site", e["links"])
        self.assertIn("main_channel", e["links"])                      # copy of the default, plus the new one
        self.assertNotIn("site", store.effective(None)["links"])      # default untouched
        store.reset_links(CH)
        self.assertNotIn("site", store.effective(CH)["links"])

    def test_template_and_toggles_are_per_channel(self):
        store.ensure_channel(CH, "A")
        store.ensure_channel(-1009, "B")
        store.update(CH, template="minimal", caption=False)
        self.assertEqual(store.effective(CH)["template_key"], "minimal")
        self.assertFalse(store.effective(CH)["caption"])
        self.assertEqual(store.effective(-1009)["template_key"], "roaroic")
        self.assertTrue(store.effective(-1009)["caption"])
        store.update(CH, template="custom", custom_template="{original_caption} hi")
        self.assertEqual(store.effective(CH)["template"], "{original_caption} hi")

    def test_buttons_old_links_and_validation(self):
        store.ensure_channel(CH, "A")
        store.set_buttons(CH, [{"text": "x", "url": "https://t.me/aaaa", "junk": 1}])
        self.assertEqual(store.buttons(CH), [{"text": "x", "url": "https://t.me/aaaa"}])
        self.assertIsNotNone(store.set_link(CH, "bad", "javascript:alert(1)"))
        self.assertEqual(store.add_old_links(CH, ["@old", "@OLD", "https://t.me/o2"]), 2)
        self.assertEqual(store.effective(CH)["old_links"], ["@old", "https://t.me/o2"])
        store.clear_old_links(CH)
        self.assertEqual(store.effective(CH)["old_links"], [])

    def test_persistence_roundtrip_and_backup(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        store.init(path)
        store.ensure_channel(CH, "Persist")
        store.set_buttons(CH, [{"text": "T", "url": "https://t.me/tttt"}])
        raw = store.export_json()
        store.init(path)                                               # "restart"
        self.assertEqual(store.buttons(CH)[0]["text"], "T")
        store.init(store.MEMORY)
        self.assertEqual(store.list_channels(), [])
        self.assertTrue(store.import_json(raw)[0])
        self.assertEqual(store.buttons(CH)[0]["url"], "https://t.me/tttt")
        self.assertFalse(store.import_json(b"nope")[0])
        self.assertFalse(store.import_json(b'{"a":1}')[0])

    def test_corrupt_file_does_not_crash(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        with open(path, "w") as f:
            f.write("{broken")
        import logging
        logging.disable(logging.CRITICAL)
        try:
            store.init(path)
        finally:
            logging.disable(logging.NOTSET)
        self.assertEqual(store.list_channels(), [])


class TestInputsAndTemplates(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(inputs.parse_link_line("Backup | @roaroic0"), ("backup", "https://t.me/roaroic0", None))
        self.assertEqual(inputs.parse_link_line("site https://example.com")[:2], ("site", "https://example.com"))
        self.assertIsNotNone(inputs.parse_link_line("x | nope")[2])
        self.assertEqual(inputs.parse_old_links("@abcd https://t.me/xyzw, junk"), ["@abcd", "https://t.me/xyzw"])
        self.assertEqual(inputs.parse_channel_ref("-1001234567890"), CH)
        self.assertEqual(inputs.parse_channel_ref("1234567890"), CH)
        self.assertEqual(inputs.parse_channel_ref("https://t.me/c/1234567890/55"), CH)
        self.assertEqual(inputs.parse_channel_ref("t.me/FilmsChor"), "@FilmsChor")
        self.assertEqual(inputs.parse_channel_ref("@FilmsChor"), "@FilmsChor")
        self.assertIsNone(inputs.parse_channel_ref("hello"))
        self.assertIsNone(inputs.parse_button_text("x" * 41)[0])

    def test_every_preset_is_valid(self):
        store.init(store.MEMORY)
        links = store.effective(None)["links"]
        for key in templates.PRESETS:
            self.assertIn("{original_caption}", templates.resolve(key, "", links), key)
        ok, err = validate_template(templates.resolve("quote", "", links), list(links))
        self.assertTrue(ok, err)


class TestScreens(unittest.TestCase):
    def test_callback_data_fits_64_bytes_and_screens_build(self):
        store.init(store.MEMORY)
        store.ensure_channel(CH, "Title <b>&</b> " * 5)
        store.set_link(CH, "a_very_long_link_name1", "https://t.me/longname")
        store.set_buttons(CH, [{"text": "B" * 40, "url": "https://t.me/bbbb"}] * 3)
        k = str(CH)
        screens = [ui.main_screen(), ui.help_screen(), ui.channels_screen(0), ui.channel_screen(k), ui.channel_screen("d"),
                   ui.template_screen(k), ui.template_screen("d"), ui.links_screen(k), ui.link_screen(k, "a_very_long_link_name1"),
                   ui.oldlinks_screen(k), ui.buttons_screen(k), ui.button_screen(k, 0), ui.run_screen(k),
                   ui.confirm_remove_screen(k), ui.confirm_clear_buttons(k), ui.custom_template_prompt(k),
                   ui.run_range_prompt(k, "both"), ui.button_add_prompt(1, k), ui.buttons_many_prompt(k)]
        for text, rows in screens:
            self.assertLess(len(text), 4096)
            for row in rows:
                for b in row:
                    self.assertLessEqual(len(b["data"].encode()), 64, b)
                    self.assertTrue(b["text"])

    def test_many_channels_are_paged(self):
        store.init(store.MEMORY)
        for i in range(20):
            store.ensure_channel(-1000000000000 - i, f"Ch {i:02d}")
        _, rows = ui.channels_screen(1)
        self.assertEqual(sum(1 for r in rows if r[0]["data"].startswith("ch:")), 8)


class Msg(types.SimpleNamespace):
    pass


def make_post(i=5, caption="Movie 2024", media=True, markup=None, text=None):
    cap = types.SimpleNamespace(html=caption) if caption else None
    return Msg(id=i, chat=types.SimpleNamespace(id=CH, title="Movies"), caption=cap,
               document=types.SimpleNamespace(file_name="m.mkv") if media else None, video=None, audio=None,
               animation=None, voice=None, photo=None, text=text, reply_markup=markup, empty=False)


class FakeClient:
    def __init__(self):
        self.calls = []

    async def edit_message_caption(self, chat, mid, caption, reply_markup=None):
        self.calls.append(("caption", mid, caption, reply_markup))

    async def edit_message_reply_markup(self, chat, mid, reply_markup=None):
        self.calls.append(("markup", mid, reply_markup))

    async def send_message(self, chat, text, **kw):
        self.calls.append(("send", chat, text, kw.get("reply_markup")))
        return types.SimpleNamespace(edit_text=self._noop)

    async def _noop(self, *a, **k):
        pass

    async def get_messages(self, chat, ids):
        return [make_post(i) for i in ids]


class TestRunner(unittest.TestCase):
    def setUp(self):
        store.init(store.MEMORY)
        store.ensure_channel(CH, "Movies")
        store.set_buttons(CH, [{"text": "A", "url": "https://t.me/aaaa"}, {"text": "B", "url": "https://t.me/bbbb"}])

    def test_auto_edits_caption_and_adds_buttons(self):
        c = FakeClient()
        self.assertEqual(run(runner.apply(c, make_post(), "auto")), "edited")
        kind, mid, cap, mk = c.calls[0]
        self.assertEqual(kind, "caption")
        self.assertIn("Movie 2024", cap)
        self.assertEqual([r[0].url for r in mk.inline_keyboard], ["https://t.me/aaaa", "https://t.me/bbbb"])

    def test_switches_and_modes(self):
        c = FakeClient()
        store.update(CH, caption=False)
        run(runner.apply(c, make_post(), "auto"))
        self.assertEqual(c.calls[-1][0], "markup")                      # caption OFF -> buttons only
        store.update(CH, buttons_on=False)
        self.assertEqual(run(runner.apply(c, make_post(), "auto")), "skip")   # both OFF -> nothing
        self.assertEqual(run(runner.apply(c, make_post(), "caption")), "edited")  # explicit run ignores switches
        store.update(CH, per_row=2)
        run(runner.apply(c, make_post(), "buttons"))
        self.assertEqual(len(c.calls[-1][2].inline_keyboard), 1)       # 2 per row -> one row of two
        self.assertEqual(len(c.calls[-1][2].inline_keyboard[0]), 2)

    def test_text_posts_get_buttons_only_and_unbutton(self):
        c = FakeClient()
        run(runner.apply(c, make_post(media=False, caption=None, text="hello"), "auto"))
        self.assertEqual(c.calls[-1][0], "markup")
        self.assertEqual(run(runner.apply(c, make_post(), "unbutton")), "skip")       # nothing to remove
        has = make_post(markup=fake_pyrogram.Markup([[fake_pyrogram.Btn("x", url="https://t.me/a")]]))
        self.assertEqual(run(runner.apply(c, has, "unbutton")), "edited")
        self.assertIsNone(c.calls[-1][2])

    def test_caption_only_keeps_existing_url_keyboard(self):
        c = FakeClient()
        store.set_buttons(CH, [])
        mk = fake_pyrogram.Markup([[fake_pyrogram.Btn("x", url="https://t.me/a")]])
        run(runner.apply(c, make_post(markup=mk), "auto"))
        self.assertIs(c.calls[-1][3], mk)

    def test_old_posts_job_counts_and_releases(self):
        c = FakeClient()
        runner.DELAY = 0
        status = types.SimpleNamespace(edit_text=c._noop)
        self.assertTrue(jobs.acquire("old posts"))
        run(runner._job(c, CH, "both", 1, 5, 1, status))
        self.assertIsNone(jobs.busy())
        self.assertEqual(sum(1 for x in c.calls if x[0] == "caption"), 5)
        self.assertIn("Updated: 5", c.calls[-1][2])


class FakeCQ:
    def __init__(self, data, uid=1):
        self.data, self.from_user = data, types.SimpleNamespace(id=uid)
        self.shown, self.answers = [], []
        self.message = types.SimpleNamespace(chat=types.SimpleNamespace(id=uid), edit_text=self._edit)

    async def _edit(self, text, **k):
        self.shown.append(text)

    async def answer(self, text="", show_alert=False):
        self.answers.append((text, show_alert))


class FakeMsg:
    def __init__(self, text, uid=1):
        self.text, self.from_user = text, types.SimpleNamespace(id=uid)
        self.sent = []

    async def reply_text(self, text, **k):
        self.sent.append(text)
        return types.SimpleNamespace(edit_text=FakeClient()._noop)


class TestPanelFlows(unittest.TestCase):
    def setUp(self):
        store.init(store.MEMORY)
        pending.clear(1)
        store.ensure_channel(CH, "Movies")
        from plugins import panel
        self.panel, self.client = panel, FakeClient()

    def tap(self, data):
        cq = FakeCQ(data)
        run(self.panel.on_callback(self.client, cq))
        return cq

    def type(self, text):
        m = FakeMsg(text)
        run(self.panel.on_input(self.client, m))
        return m

    def test_create_a_button_step_by_step(self):
        cq = self.tap(f"bta:{CH}")
        self.assertIn("step 1/2", cq.shown[-1])
        self.assertIn("step 2/2", self.type("🎬 Movies").sent[-1])
        m = self.type("@roaroic1")
        self.assertIn("Button added", m.sent[-1])
        self.assertEqual(store.buttons(CH), [{"text": "🎬 Movies", "url": "https://t.me/roaroic1"}])
        self.assertIsNone(pending.get(1))

    def test_bad_input_keeps_waiting(self):
        self.tap(f"bta:{CH}")
        self.assertIn("Too long", self.type("x" * 60).sent[-1])
        self.assertEqual(pending.get(1)["kind"], "btn_text")
        self.tap(f"ch:{CH}")                                            # tapping another menu cancels the step
        self.assertIsNone(pending.get(1))

    def test_add_many_edit_move_delete(self):
        self.tap(f"btm:{CH}")
        self.type("One | https://t.me/oneone\nTwo | @twotwo\nbad line")
        self.assertEqual([b["text"] for b in store.buttons(CH)], ["One", "Two"])
        self.tap(f"btd:{CH}:0")
        self.assertEqual([b["text"] for b in store.buttons(CH)], ["Two", "One"])
        self.tap(f"bte:{CH}:0:t")
        self.type("Renamed")
        self.assertEqual(store.buttons(CH)[0]["text"], "Renamed")
        self.tap(f"btx:{CH}:1")
        self.assertEqual(len(store.buttons(CH)), 1)
        self.tap(f"btr:{CH}:2")
        self.assertEqual(store.get(CH)["per_row"], 2)

    def test_links_template_toggle_flows(self):
        self.tap(f"lka:{CH}")
        self.type("Website | https://example.com/a")
        self.assertEqual(store.effective(CH)["links"]["website"], "https://example.com/a")
        self.tap(f"tpc:{CH}")
        self.assertIn("original_caption", self.type("no placeholder here").sent[-1])    # rejected, still waiting
        self.assertEqual(pending.get(1)["kind"], "tpl_custom")
        self.assertNotEqual(store.effective(CH)["template_key"], "custom")
        self.type('{original_caption}\n<a href="{website}">Site</a>')
        self.assertEqual(store.effective(CH)["template_key"], "custom")
        self.tap(f"tps:{CH}:minimal")
        self.assertEqual(store.effective(CH)["template_key"], "minimal")
        self.tap(f"tps:{CH}:inherit")
        self.assertFalse(store.effective(CH)["own_template"])
        self.tap(f"tg:{CH}:cap")
        self.assertFalse(store.effective(CH)["caption"])
        cq = self.tap(f"rmy:{CH}")
        self.assertEqual(store.list_channels(), [])
        self.assertTrue(cq.shown)

    def test_run_on_old_posts_flow(self):
        store.set_buttons(CH, [{"text": "A", "url": "https://t.me/aaaa"}])
        runner.DELAY = 0

        async def go():
            cq = FakeCQ(f"rm:{CH}:both")
            await self.panel.on_callback(self.client, cq)
            m = FakeMsg("3")
            await self.panel.on_input(self.client, m)
            await asyncio.gather(*list(runner._tasks))
            return cq, m
        cq, m = run(go())
        self.assertEqual(sum(1 for x in self.client.calls if x[0] == "caption"), 3)
        self.assertIsNone(jobs.busy())

    def test_run_buttons_requires_buttons_and_only_owner_data(self):
        cq = self.tap(f"rm:{CH}:buttons")
        self.assertTrue(cq.answers[-1][1])                              # alert shown
        self.assertIsNone(pending.get(1))

    def test_preview_and_backup(self):
        self.tap("pv:d")
        self.assertTrue(any(c[0] == "send" for c in self.client.calls))
        self.assertTrue(store.export_json().startswith(b"{"))


if __name__ == "__main__":
    unittest.main()
