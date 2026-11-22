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
        store.set_user(1)                                   # admin sees every channel
        self.addCleanup(store.set_user, None)
        for i in range(20):
            store.ensure_channel(-1000000000000 - i, f"Ch {i:02d}")
        _, rows = ui.channels_screen(1)
        self.assertEqual(sum(1 for r in rows if r[0]["data"].startswith("ch:")), 8)


class TestNoPreview(unittest.TestCase):
    def test_uses_whichever_keyword_the_library_has(self):
        from utils import tg

        def old(text, disable_web_page_preview=None): ...

        def new(text, link_preview_options=None): ...

        def neither(text): ...
        self.assertEqual(tg.nopreview(old), {"disable_web_page_preview": True})
        self.assertEqual(list(tg.nopreview(new)), [])            # fake pyrogram has no LinkPreviewOptions -> safe empty
        self.assertEqual(tg.nopreview(neither), {})


class TestDesignsAndLook(unittest.TestCase):
    def setUp(self):
        store.init(store.MEMORY)

    def test_all_20_designs_are_valid_stable_and_fit(self):
        from utils.captions import ROAROIC_LINKS, build_caption, visible_len
        from utils.designs import DESIGNS
        self.assertEqual(len(DESIGNS), 20)
        for key, (name, tpl) in DESIGNS.items():
            ok, err = validate_template(tpl, list(ROAROIC_LINKS))
            self.assertTrue(ok, f"{key}: {err}")
            for original in ("Pushpa 2 (2024) 1080p WEB-DL", "<b>Bold Title</b> extra", "Movie 🎬 (2023)"):
                once = build_caption(original, tpl, ROAROIC_LINKS, [], None)
                twice = build_caption(once, tpl, ROAROIC_LINKS, [], None)
                self.assertEqual(once, twice, f"{key} changes when run again")
                self.assertLessEqual(visible_len(once), 1024)
                self.assertTrue("t.me/" in once or "@roaroic" in once, key)   # links really got filled in
                self.assertNotIn("{", once, key)

    def test_designs_skip_lines_for_missing_links(self):
        from utils.captions import build_caption
        from utils.designs import DESIGNS
        out = build_caption("Title", DESIGNS["d02"][1], {"main_channel": "https://t.me/onlyone"}, [], None)
        self.assertIn("Main Channel", out)
        self.assertNotIn("Backup", out)
        self.assertNotIn("{", out)

    def test_designs_are_selectable_and_resolve(self):
        store.ensure_channel(CH, "A")
        store.update(CH, template="d07")
        self.assertIn("{main_channel_at}", store.effective(CH)["template"])
        self.assertIn("🎬", templates.name("d01") + "🎬")
        self.assertEqual(len(templates.PRESETS), 25)

    def test_fonts(self):
        from utils.fonts import fancy
        self.assertEqual(fancy("Join 1", "normal"), "Join 1")
        self.assertEqual(fancy("Aa 1 🎬", "bold"), "𝗔𝗮 𝟭 🎬")
        self.assertEqual(fancy("Join", "small"), "ᴊᴏɪɴ")
        self.assertEqual(fancy("abc", "mono"), "𝚊𝚋𝚌")
        self.assertEqual(fancy("x", "nonsense"), "x")

    def test_layouts(self):
        from utils.buttons import build_rows
        bs = [{"text": str(i), "url": "u"} for i in range(5)]
        self.assertEqual([len(r) for r in build_rows(bs, 1)], [1] * 5)
        self.assertEqual([len(r) for r in build_rows(bs, 2)], [2, 2, 1])
        self.assertEqual([len(r) for r in build_rows(bs, 3)], [3, 2])
        self.assertEqual([len(r) for r in build_rows(bs, 0)], [1, 2, 2])      # smart: first wide, then pairs
        self.assertEqual(build_rows([], 0), [])

    def test_markup_applies_font_and_colour_mode(self):
        from utils import tg
        bs = [{"text": "Join", "url": "https://t.me/aaaa"}, {"text": "Bot", "url": "https://t.me/bbbb"}]
        mk = tg.url_markup(bs, 2, "auto", "bold")
        self.assertEqual([b.text for b in mk.inline_keyboard[0]], ["𝗝𝗼𝗶𝗻", "𝗕𝗼𝘁"])
        calls = []
        orig = tg._make_button
        tg._make_button = lambda text, slot, **kw: (calls.append(slot["style"]), orig(text, {"style": None, "prefix": ""}, **kw))[1]
        try:
            tg.url_markup(bs, 1, "auto")
            tg.url_markup(bs, 1, "danger")
            tg.url_markup(bs, 1, "none")
        finally:
            tg._make_button = orig
        self.assertEqual(calls, ["primary", "success", "danger", "danger", None, None])

    def test_store_validates_look_fields(self):
        store.ensure_channel(CH, "A")
        store.update(CH, color="purple", font="comic", per_row=9)
        raw = store.export_json()
        store.init(store.MEMORY)
        store.import_json(raw)
        c = store.get(CH)
        self.assertEqual((c["color"], c["font"], c["per_row"]), ("auto", "normal", 1))


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

    async def get_chat(self, ref):
        if isinstance(ref, int) and ref == -1009:
            raise fake_pyrogram.RPCError()
        cid = ref if isinstance(ref, int) else CH
        return types.SimpleNamespace(id=cid, title="Real <Title>", username="movies_pub",
                                     type=types.SimpleNamespace(name="CHANNEL"))

    admins = {1, 2}                                         # users that are admins of the fake channel

    async def get_chat_member(self, chat, who):
        if who == "me":
            return types.SimpleNamespace(status=types.SimpleNamespace(name="ADMINISTRATOR"), privileges=None)
        name = "ADMINISTRATOR" if who in self.admins else "MEMBER"
        return types.SimpleNamespace(status=types.SimpleNamespace(name=name))


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

    def tap(self, data, uid=1):
        cq = FakeCQ(data, uid)
        run(self.panel.on_callback(self.client, cq))
        return cq

    def type(self, text, uid=1):
        m = FakeMsg(text, uid)
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

    def test_template_pages_pick_a_design_and_button_look(self):
        cq = self.tap(f"tpl:{CH}")
        self.assertTrue(cq.shown)
        self.assertIn("1/4", [b["text"] for r in ui.template_screen(str(CH), 0)[1] for b in r])
        for page in range(4):
            text, rows = ui.template_screen(str(CH), page)
            for r in rows:
                for b in r:
                    self.assertLessEqual(len(b["data"].encode()), 64, b)
        self.tap(f"tps:{CH}:d13:1")
        self.assertEqual(store.effective(CH)["template_key"], "d13")
        self.assertIn("Title", store.effective(CH)["template"])
        self.tap(f"tps:{CH}:inherit:0")
        self.assertFalse(store.effective(CH)["own_template"])
        self.tap(f"btr:{CH}:3")
        self.tap(f"btcol:{CH}:danger")
        self.tap(f"btf:{CH}:small")
        e = store.effective(CH)
        self.assertEqual((e["per_row"], e["color"], e["font"]), (3, "danger", "small"))
        self.tap(f"btr:{CH}:0")
        self.assertEqual(store.effective(CH)["per_row"], 0)
        self.tap(f"btcol:{CH}:bogus")
        self.assertEqual(store.effective(CH)["color"], "danger")           # unknown values are ignored

    def test_run_buttons_requires_buttons_and_only_owner_data(self):
        cq = self.tap(f"rm:{CH}:buttons")
        self.assertTrue(cq.answers[-1][1])                              # alert shown
        self.assertIsNone(pending.get(1))

    def test_channel_list_shows_name_link_id(self):
        store.ensure_channel(-1009, "Gone")
        pages = run(self.panel.channel_list_pages(self.client))
        text = "\n".join(pages)
        self.assertIn("Real &lt;Title&gt;", text)
        self.assertIn("https://t.me/movies_pub", text)
        self.assertIn(str(CH), text)
        self.assertIn("can't open", text)
        store.init(store.MEMORY)
        self.assertIn("No channels", run(self.panel.channel_list_pages(self.client))[0])
        self.assertTrue(any(b["data"] == "cl" for r in ui.channels_screen(0)[1] for b in r))

    def test_preview_and_backup(self):
        self.tap("pv:d")
        self.assertTrue(any(c[0] == "send" for c in self.client.calls))
        self.assertTrue(store.export_json().startswith(b"{"))


class TestMultiUser(unittest.TestCase):
    """Normal users (id 2, 3) each manage only their own channels; id 1 is the bot admin (OWNER_ID)."""

    def setUp(self):
        store.init(store.MEMORY)
        for u in (1, 2, 3):
            pending.clear(u)
        from plugins import panel
        self.panel, self.client = panel, FakeClient()
        self.cfg = __import__("config")
        self.addCleanup(setattr, self.cfg, "PUBLIC_MODE", self.cfg.PUBLIC_MODE)
        self.addCleanup(setattr, self.cfg, "MAX_CHANNELS_PER_USER", self.cfg.MAX_CHANNELS_PER_USER)

    def tap(self, data, uid):
        cq = FakeCQ(data, uid)
        run(self.panel.on_callback(self.client, cq))
        return cq

    def type(self, text, uid):
        m = FakeMsg(text, uid)
        run(self.panel.on_input(self.client, m))
        return m

    def test_user_adds_own_channel_and_only_sees_it(self):
        store.ensure_channel(-1009, "Someone else", owner=3)
        self.tap("add", 2)
        m = self.type("@movies_pub", 2)
        self.assertIn("Channel added", m.sent[-1])
        self.assertEqual(store.owner_of(CH), 2)
        self.assertEqual([k for k, _ in store.my_channels(2)], [str(CH)])
        self.assertEqual([k for k, _ in store.my_channels(3)], ["-1009"])
        self.assertEqual(len(store.my_channels(1)), 2)               # admin sees all

    def test_must_be_channel_admin_to_add(self):
        self.tap("add", 3)                                           # user 3 is not an admin of the fake channel
        m = self.type("@movies_pub", 3)
        self.assertIn("must be an admin", m.sent[-1])
        self.assertIsNone(store.get(CH))

    def test_cannot_touch_other_users_channel(self):
        store.ensure_channel(CH, "Mine", owner=2)
        for data in (f"ch:{CH}", f"bta:{CH}", f"tg:{CH}:cap", f"rmy:{CH}", f"lkd:{CH}:main_channel"):
            cq = self.tap(data, 3)
            self.assertEqual(cq.answers[-1], ("This channel is not yours.", True), data)
            self.assertFalse(cq.shown, data)
        self.assertIsNotNone(store.get(CH))
        self.assertTrue(store.get(CH)["caption"])
        self.assertTrue(self.tap(f"ch:{CH}", 2).shown)               # the owner can
        self.assertTrue(self.tap(f"ch:{CH}", 1).shown)               # and so can the admin

    def test_channel_already_claimed_by_someone_else(self):
        store.ensure_channel(CH, "Taken", owner=3)
        self.client.admins = {1, 2, 3}
        self.tap("add", 2)
        self.assertIn("already managed", self.type("@movies_pub", 2).sent[-1])
        self.assertEqual(store.owner_of(CH), 3)

    def test_unowned_legacy_channel_can_be_claimed_by_its_admin(self):
        store.ensure_channel(CH, "Old")                              # registered before multi-user: no owner
        self.assertFalse(store.can_manage(2, CH))
        self.tap("add", 2)
        self.type("@movies_pub", 2)
        self.assertEqual(store.owner_of(CH), 2)

    def test_channel_limit(self):
        self.cfg.MAX_CHANNELS_PER_USER = 1
        store.ensure_channel(-1009, "Another", owner=2)
        self.tap("add", 2)
        self.assertIn("up to 1", self.type("@movies_pub", 2).sent[-1])
        self.assertIsNone(store.get(CH))

    def test_each_user_has_private_default_settings(self):
        store.ensure_channel(CH, "A", owner=2)
        store.ensure_channel(-1009, "B", owner=3)
        self.tap("lka:d", 2)
        self.type("Mine | https://example.com/two", 2)
        self.assertIn("mine", store.effective(CH)["links"])           # 2's channel inherits 2's defaults
        self.assertNotIn("mine", store.effective(-1009)["links"])     # 3's does not
        store.set_user(3)
        self.addCleanup(store.set_user, None)
        self.assertNotIn("mine", store.effective(None)["links"])
        store.set_user(2)
        self.assertIn("mine", store.effective(None)["links"])
        self.assertNotIn("mine", store.effective(-1009)["links"])

    def test_private_mode_and_bans(self):
        self.cfg.PUBLIC_MODE = False
        self.assertFalse(store.user_allowed(2))
        self.assertTrue(store.user_allowed(1))
        self.cfg.PUBLIC_MODE = True
        self.assertTrue(store.user_allowed(2))
        store.ban(2)
        self.assertFalse(store.user_allowed(2))
        store.ban(1)
        self.assertTrue(store.user_allowed(1))                        # admins cannot be banned
        store.ban(2, False)
        self.assertTrue(store.user_allowed(2))

    def test_admin_only_buttons_and_job_stop(self):
        self.assertIn("Admins only", self.tap("st", 2).answers[-1][0])
        self.assertIn("Admins only", self.tap("bk", 2).answers[-1][0])
        self.assertTrue(self.tap("st", 1).shown)
        self.assertTrue(jobs.acquire("old posts", 2))
        try:
            self.assertFalse(jobs.request_stop(3))                   # another normal user cannot stop it
            self.assertTrue(jobs.request_stop(2))
            self.assertTrue(jobs.request_stop(1))                    # admin can
        finally:
            jobs.release()

    def test_unclaimed_channel_posts_are_ignored_in_public_mode(self):
        from plugins import captions
        captions._told.clear()
        post = make_post()
        run(captions.on_channel_post(self.client, post))
        self.assertEqual([c for c in self.client.calls if c[0] in ("caption", "markup")], [])
        self.assertIsNone(store.get(CH))                              # not auto-registered
        store.ensure_channel(CH, "Claimed", owner=2)
        run(captions.on_channel_post(self.client, make_post()))
        self.assertTrue(any(c[0] == "caption" for c in self.client.calls))

    def test_private_mode_auto_registers_for_the_owner(self):
        from plugins import captions
        self.cfg.PUBLIC_MODE = False
        run(captions.on_channel_post(self.client, make_post()))
        self.assertEqual(store.owner_of(CH), 1)
        self.assertTrue(any(c[0] == "caption" for c in self.client.calls))

    def test_oldposts_command_requires_own_channel(self):
        from plugins import oldposts
        store.ensure_channel(CH, "Mine", owner=2)
        m = FakeMsg("/oldposts 5", 3)
        m.command = ["oldposts", str(CH), "5"]
        run(oldposts.oldposts_cmd(self.client, m))
        self.assertIn("not in your list", m.sent[-1])


if __name__ == "__main__":
    unittest.main()
