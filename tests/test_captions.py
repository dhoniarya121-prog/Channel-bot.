import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import settings  # noqa: E402
from utils import captioning, captions  # noqa: E402


class TestCaptions(unittest.TestCase):
    LINKS = {"main_channel": "https://t.me/mainch", "backup_channel": "https://t.me/backupch",
             "movie_bot": "https://t.me/moviebot", "discussion_group": "https://t.me/groupchat"}

    def build(self, original, **kw):
        return captions.build_caption(original, captions.DEFAULT_TEMPLATE, self.LINKS, **kw)

    def test_default_template_output(self):
        out = self.build("Avatar (2022)")
        self.assertTrue(out.startswith("🎬 Avatar (2022)\n\n💎 Main Channel: "))
        for key, label in (("mainch", "Join Now"), ("backupch", "Join Now"), ("moviebot", "Start Bot"),
                           ("groupchat", "Join Group")):
            self.assertIn(f'<a href="https://t.me/{key}">{label}</a>', out)

    def test_html_in_original_is_preserved(self):
        out = self.build("<b>Avatar</b> &amp; Friends")
        self.assertIn("🎬 <b>Avatar</b> &amp; Friends", out)

    def test_no_caption_uses_file_name(self):
        self.assertIn("🎬 Great Movie 2020", self.build("", file_name="Great_Movie 2020.mkv"))
        self.assertIn("🎬 New File", self.build(None))

    def test_long_caption_is_truncated_safely(self):
        out = self.build("A" * 3000)
        self.assertLessEqual(captions.visible_len(out), 1024)
        self.assertIn("…", out)
        self.assertIn('href="https://t.me/mainch"', out)           # footer survives
        emoji = self.build("😀" * 2000)
        self.assertLessEqual(captions.visible_len(emoji), 1024)

    def test_duplicate_links_are_not_added_twice(self):
        once = self.build("Avatar")
        twice = self.build(once)                                    # re-processing a processed caption
        self.assertEqual(once, twice)
        self.assertEqual(once.count("https://t.me/mainch"), 1)
        mixed = self.build("Avatar\nJoin https://t.me/mainch now\nsee @backupch")
        self.assertEqual(mixed.count("t.me/mainch"), 1)
        self.assertNotIn("@backupch", mixed)
        links = dict(self.LINKS, backup_channel=self.LINKS["main_channel"])
        out = captions.build_caption("X", captions.DEFAULT_TEMPLATE, links)
        self.assertEqual(out.count("t.me/mainch"), 1)               # same URL twice in config -> once

    def test_old_links_are_replaced(self):
        out = self.build("Avatar\nJoin https://t.me/oldchannel\nBy @oldchannel2",
                         old_links=["https://t.me/oldchannel", "https://t.me/oldchannel2"])
        self.assertNotIn("oldchannel", out)
        self.assertIn("🎬 Avatar", out)

    def test_unset_links_drop_their_line(self):
        links = dict(self.LINKS, movie_bot="")
        out = captions.build_caption("X", captions.DEFAULT_TEMPLATE, links)
        self.assertNotIn("Movie Bot", out)
        self.assertIn("Main Channel", out)

    def test_template_validation(self):
        ok, _ = captions.validate_template(captions.DEFAULT_TEMPLATE)
        self.assertTrue(ok)
        for bad in ("", "no placeholder", "{original_caption} {nope}", "{original_caption} <script>x</script>",
                    "{original_caption} <b>open", '{original_caption} <a>x</a>'):
            self.assertFalse(captions.validate_template(bad)[0], bad)
        self.assertTrue(captions.validate_url("https://t.me/abc"))
        for bad in ("t.me/abc", "javascript:alert(1)", 'https://t.me/"x', ""):
            self.assertFalse(captions.validate_url(bad), bad)


class TestChannelButtons(unittest.TestCase):
    def test_parse_lines_and_errors(self):
        from utils.buttons import parse_lines
        ok, err = parse_lines("Main Channel | https://t.me/mainch\n\nMovie Bot|https://t.me/moviebot")
        self.assertEqual([b["text"] for b in ok], ["Main Channel", "Movie Bot"])
        self.assertEqual(err, [])
        ok, err = parse_lines("no separator\nX | not-a-url\n" + "Y" * 50 + " | https://t.me/a_b_c\n | https://t.me/x1234")
        self.assertEqual((ok, len(err)), ([], 4))

    def test_merge_dedupes_and_limits(self):
        from utils.buttons import merge, MAX_BUTTONS
        base = [{"text": "A", "url": "https://t.me/aaaa"}]
        out, added, skipped = merge(base, [{"text": "A2", "url": "https://t.me/AAAA/"}, {"text": "B", "url": "https://t.me/bbbb"}])
        self.assertEqual((len(out), added, skipped), (2, 1, 1))
        many = [{"text": str(i), "url": f"https://t.me/ch{i:04d}"} for i in range(40)]
        self.assertEqual(len(merge([], many)[0]), MAX_BUTTONS)

    def test_rows_and_post_links(self):
        from utils.buttons import build_rows, parse_post_link
        b = [{"text": str(i), "url": "u"} for i in range(5)]
        self.assertEqual([len(r) for r in build_rows(b, 1)], [1] * 5)
        self.assertEqual([len(r) for r in build_rows(b, 2)], [2, 2, 1])
        self.assertEqual(parse_post_link("https://t.me/c/1234567890/55"), (-1001234567890, 55))
        self.assertEqual(parse_post_link("t.me/FilmsChor/9?single"), ("@FilmsChor", 9))
        self.assertIsNone(parse_post_link("https://t.me/FilmsChor"))
        self.assertIsNone(parse_post_link("hello"))


class TestQuoteStyleCaptions(unittest.TestCase):
    LINKS = {"backup": "https://t.me/unrated_wolfnox", "premium": "https://t.me/wolfe_noxnetwork",
             "adult": "https://t.me/WOLFNOX_link"}

    def test_screenshot_style_quote_block(self):
        tpl = captions.build_quote_template(self.LINKS)
        self.assertTrue(captions.validate_template(tpl, list(self.LINKS))[0])
        out = captions.build_caption("Qala (2022)\nHindi • 1080p WEB-DL\n2.24 GB", tpl, self.LINKS)
        self.assertIn("Qala (2022)\nHindi • 1080p WEB-DL\n2.24 GB\n\n<blockquote>", out)
        for line in ("❶ BACKUP ➡ @unrated_wolfnox", "❷ PREMIUM ➡ @wolfe_noxnetwork", "❸ ADULT ➡ @WOLFNOX_link</blockquote>".replace("</blockquote>", "")):
            self.assertIn(line, out)
        self.assertTrue(out.rstrip().endswith("</blockquote>"))

    def test_title_with_own_handle_keeps_title_and_is_idempotent(self):
        tpl = captions.build_quote_template(self.LINKS)
        out = captions.build_caption("(@wolfe_noxnetwork) Qala (2022)\nHindi • 1080p WEB-DL\n2.24 GB", tpl, self.LINKS)
        self.assertIn("Qala (2022)", out)
        self.assertEqual(out.count("@wolfe_noxnetwork"), 1)       # only in the quote block, not duplicated
        again = captions.build_caption(out, tpl, self.LINKS)
        self.assertEqual(again, out)

    def test_dropped_line_never_leaves_unclosed_tags(self):
        links = dict(self.LINKS, adult="")
        tpl = "{original_caption}\n<blockquote>x\n{adult_at}</blockquote>"
        out = captions.build_caption("T", tpl, links)
        self.assertEqual(out.count("<blockquote>"), out.count("</blockquote>"))
        self.assertEqual(captions.autoclose("<b>a<i>b"), "<b>a<i>b</i></b>")

    def test_custom_link_names_and_unknown_placeholders(self):
        self.assertEqual(captions.make_key("Premium Plan!"), "premium_plan")
        self.assertIsNone(captions.make_key("!!!"))
        self.assertIsNone(captions.make_key("x_at"))
        self.assertEqual(captions.make_key("123"), "l_123")
        ok, err = captions.validate_template("{original_caption} {nope_at}", list(self.LINKS))
        self.assertFalse(ok)
        out = captions.render("{original_caption}\nGone {removed_link}\nHi {adult_at}", "T", self.LINKS)
        self.assertNotIn("removed_link", out)
        self.assertIn("Hi @WOLFNOX_link", out)
        self.assertEqual(captions.handle_of("https://t.me/+AbCdEf"), "t.me/+AbCdEf")

    def test_promo_only_lines_removed_real_text_kept(self):
        links = {"a": "https://t.me/mychannel"}
        out = captions.remove_known_links("Movie Name 2024\nJoin @mychannel\n❷ PREMIUM➡ @mychannel\nWatch Movie Name @mychannel", ["https://t.me/mychannel"])
        self.assertEqual(out, "Movie Name 2024\nWatch Movie Name")


class TestOldPostRange(unittest.TestCase):
    def test_parse_range(self):
        from utils.oldposts import parse_range
        self.assertEqual(parse_range("https://t.me/c/1234567890/900"), (1, 900))
        self.assertEqual(parse_range("500"), (1, 500))
        self.assertEqual(parse_range("100 900"), (100, 900))
        for bad in ("", "abc", "900 100", "0 5", "1 999999999"):
            self.assertIsNone(parse_range(bad), bad)


class TestRoaroicDesign(unittest.TestCase):
    def test_design_links_and_prefix(self):
        out = captioning.compute_caption("Movie 2026 1080p", "Movie.mkv")
        self.assertTrue(out.startswith("<b>[ @roaroic0 ]</b> Movie 2026 1080p"))
        self.assertEqual(out.count(captions.DIVIDER), 2)
        for url in captions.ROAROIC_LINKS.values():
            self.assertIn(url, out)
        self.assertTrue(out.endswith("ROAROIC MOVIE'S || 0.1</b> 💫"))
        self.assertLessEqual(captions.visible_len(out), 1024)

    def test_reedit_is_stable_and_old_footer_removed(self):
        once = captioning.compute_caption("Movie 2026 1080p", "Movie.mkv")
        self.assertEqual(captioning.compute_caption(once, "Movie.mkv"), once)
        messy = "Movie 2026 1080p\n\nJoin https://t.me/roaroic0 now"
        self.assertEqual(captioning.compute_caption(messy, "m.mkv").count("Join"), 0)

    def test_long_caption_fits(self):
        out = captioning.compute_caption("A" * 3000, "x.mkv")
        self.assertLessEqual(captions.visible_len(out), 1024)
        self.assertTrue(out.endswith("💫"))


if __name__ == '__main__':
    unittest.main()
