import asyncio
import os
import tempfile
import unittest
from datetime import timedelta

from tests import helpers  # noqa: F401  (must come first: installs stand-ins, sets owner)
from tests.helpers import fresh

helpers.install_stubs()           # Telegram-free stand-ins so utils.delivery can be imported

from database import (admins, channels, files, mongo, premium, referrals, requests, settings, sharing, users)
from utils import broadcast, captions
from utils.forcesub import evaluate
from utils.ratelimit import SlidingWindowLimiter
from utils.text import utcnow


def media(n: int, **kw):
    return {"file_id": f"fid{n}", "file_unique_id": f"uid{n}", "file_type": "document",
            "file_name": f"Movie.{n}.mkv", "file_size": 100, "caption": kw.get("caption", f"Movie {n}"),
            **{k: v for k, v in kw.items() if k != "caption"}}


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db, self._cleanup = await fresh()
        await settings.set("quota_mode", "total")          # classic one-time quota tests; daily mode has its own class

    async def asyncTearDown(self):
        await self._cleanup()

    async def new_user(self, uid, **kw):
        doc, created = await users.register(uid, kw.get("name", f"U{uid}"), kw.get("username"), kw.get("lang"))
        return doc

    async def approved_files(self, n, start=0):
        toks = []
        for i in range(start, start + n):
            d, _ = await files.submit(999, media(i), auto_approve=True)
            toks.append(d["_id"])
        return toks


class TestUsers(Base):
    async def test_registration_is_automatic_and_idempotent(self):
        doc, created = await users.register(10, "Asha", "AshaK", "hi-IN")
        self.assertTrue(created)
        self.assertEqual((doc["first_name"], doc["username_l"], doc["lang"]), ("Asha", "ashak", "hi"))
        self.assertFalse(doc["banned"])
        doc2, created2 = await users.register(10, "Asha R", "ashak")
        self.assertFalse(created2)
        self.assertEqual(doc2["first_name"], "Asha R")
        self.assertEqual(await users.count(), 1)
        self.assertEqual((await users.find("@ashak"))["_id"], 10)
        self.assertEqual((await users.find("10"))["_id"], 10)

    async def test_free_quota_is_five(self):
        doc = await self.new_user(11)
        self.assertEqual(doc["quota_remaining"], 5)
        self.assertEqual(doc["plan"], "free")

    async def test_ban_unban_and_warn_autoban(self):
        await self.new_user(12)
        self.assertTrue(await users.ban(12, "spam", 1))
        res = await users.consume_share(12)
        self.assertEqual((res.ok, res.reason), (False, "banned"))
        self.assertTrue(await users.unban(12))
        self.assertTrue((await users.consume_share(12)).ok)
        self.assertEqual(await users.warn(12, 1, "w1", 3), (1, False))
        self.assertEqual(await users.warn(12, 1, "w2", 3), (2, False))
        self.assertEqual(await users.warn(12, 1, "w3", 3), (3, True))
        self.assertTrue((await users.get(12))["banned"])

    async def test_custom_permission_blocks_sharing(self):
        await self.new_user(13)
        await users.set_permission(13, "share", False)
        self.assertEqual((await users.consume_share(13)).reason, "no_permission")
        await users.set_permission(13, "share", True)
        self.assertTrue((await users.consume_share(13)).ok)

    async def test_verification_changes_only_once(self):
        await self.new_user(14)
        self.assertTrue(await users.set_verified(14, True))
        self.assertFalse(await users.set_verified(14, True))


class TestSharingQuota(Base):
    async def test_quota_deduction_and_block_at_zero(self):
        await self.new_user(20)
        toks = await self.approved_files(7)
        results = []
        for t in toks:
            results.append(await sharing.share_file(20, t))
        self.assertEqual([r.ok for r in results], [True] * 5 + [False] * 2)
        self.assertEqual({r.reason for r in results[5:]}, {"limit"})
        doc = await users.get(20)
        self.assertEqual((doc["quota_remaining"], doc["shared_total"]), (0, 5))
        self.assertEqual(await sharing.count(20), 5)           # failed attempts leave no history

    async def test_resharing_same_file_is_free(self):
        await self.new_user(21)
        (t,) = await self.approved_files(1)
        self.assertEqual((await sharing.share_file(21, t)).reason, "ok")
        again = await sharing.share_file(21, t)
        self.assertEqual((again.ok, again.reason), (True, "already"))
        self.assertEqual((await users.get(21))["quota_remaining"], 4)

    async def test_premium_unlimited_sharing(self):
        await self.new_user(22)
        await premium.activate(22, 7, 1)
        toks = await self.approved_files(12)
        res = [await sharing.share_file(22, t) for t in toks]
        self.assertTrue(all(r.ok and r.mode == "unlimited" for r in res))
        self.assertEqual((await users.get(22))["quota_remaining"], 5)

    async def test_admin_granted_unlimited_and_custom_limit(self):
        await self.new_user(23)
        await users.set_quota(23, 2)
        toks = await self.approved_files(4)
        self.assertEqual([(await sharing.share_file(23, t)).ok for t in toks], [True, True, False, False])
        await users.set_unlimited(23, True)
        self.assertTrue((await sharing.share_file(23, toks[2])).ok)
        await users.set_unlimited(23, False)
        self.assertEqual((await sharing.share_file(23, toks[3])).reason, "limit")

    async def test_admin_quota_reset(self):
        await self.new_user(24)
        toks = await self.approved_files(6)
        for t in toks:
            await sharing.share_file(24, t)
        self.assertEqual((await users.get(24))["quota_remaining"], 0)
        self.assertEqual(await users.reset_quota(24), 5)
        self.assertTrue((await sharing.share_file(24, toks[5])).ok)
        await settings.set("free_quota", 9)
        self.assertEqual(await users.reset_quota(24), 9)
        self.assertEqual(await users.reset_all_free_quota(), 1)

    async def test_concurrent_requests_cannot_overspend(self):
        await self.new_user(25)
        toks = await self.approved_files(30)
        res = await asyncio.gather(*(sharing.share_file(25, t) for t in toks))
        self.assertEqual(sum(r.ok for r in res), 5)
        doc = await users.get(25)
        self.assertEqual((doc["quota_remaining"], doc["shared_total"]), (0, 5))
        self.assertEqual(await sharing.count(25), 5)

    async def test_concurrent_requests_same_file_spend_once(self):
        await self.new_user(26)
        (t,) = await self.approved_files(1)
        res = await asyncio.gather(*(sharing.share_file(26, t) for _ in range(20)))
        self.assertTrue(all(r.ok for r in res))
        self.assertEqual(sorted({r.reason for r in res}), ["already", "ok"])
        self.assertEqual(sum(r.reason == "ok" for r in res), 1)
        self.assertEqual((await users.get(26))["quota_remaining"], 4)

    async def test_sharing_toggle_and_access_control(self):
        await self.new_user(27)
        toks = await self.approved_files(2)
        await files.set_visibility(toks[0], "premium")
        self.assertEqual((await sharing.share_file(27, toks[0])).reason, "premium_only")
        pending, _ = await files.submit(27, media(50))
        self.assertEqual((await sharing.share_file(27, pending["_id"])).reason, "pending")
        self.assertEqual((await sharing.share_file(27, "nope")).reason, "no_file")
        await settings.set("sharing_enabled", False)
        self.assertEqual((await sharing.share_file(27, toks[1])).reason, "disabled")


class TestFiles(Base):
    async def test_submission_approval_and_search(self):
        d, created = await files.submit(30, media(1, caption="Avatar 2022 1080p"))
        self.assertTrue(created)
        self.assertEqual(d["status"], "pending")
        dup, created2 = await files.submit(31, media(1))
        self.assertFalse(created2)
        self.assertEqual(dup["_id"], d["_id"])
        rows, total = await files.search("avatar")
        self.assertEqual(total, 0)                       # pending files are not searchable
        self.assertIsNotNone(await files.approve(d["_id"], 1))
        self.assertIsNone(await files.approve(d["_id"], 1))   # second click is a no-op
        rows, total = await files.search("avatar 1080p")
        self.assertEqual((total, rows[0]["_id"]), (1, d["_id"]))
        self.assertEqual(len({(await files.submit(1, media(i)))[0]["_id"] for i in range(60, 80)}), 20)

    async def test_channel_index_is_deduplicated(self):
        a, c1 = await files.add_channel_file(-100123, 5, media(70))
        b, c2 = await files.add_channel_file(-100123, 5, media(70))
        self.assertEqual((c1, c2, a["_id"]), (True, False, b["_id"]))


class TestPremium(Base):
    async def test_activate_renew_expire_notify(self):
        await self.new_user(40)
        end1 = await premium.activate(40, 7, 1)
        end2 = await premium.activate(40, 30, 1)             # renewal extends from current end
        self.assertEqual(end2 - end1, timedelta(days=30))
        self.assertTrue((await premium.status(40))["active"])
        self.assertEqual(await premium.count_active(), 1)
        with self.assertRaises(ValueError):
            await premium.activate(40, 0, 1)
        # notice 3 days before the end (claimed once)
        due = await premium.due_for_notice([3, 1], now=utcnow() + timedelta(days=35))
        self.assertEqual([(u, b) for u, b, _ in due], [(40, 3)])
        self.assertEqual(await premium.due_for_notice([3, 1], now=utcnow() + timedelta(days=35)), [])
        # expiry
        later = utcnow() + timedelta(days=40)
        self.assertEqual(await premium.expire_due(now=later), [40])
        self.assertEqual(await premium.expire_due(now=later), [])
        self.assertEqual((await users.get(40))["plan"], "free")

    async def test_revoke_and_unknown_user(self):
        self.assertIsNone(await premium.activate(404, 7, 1))
        await self.new_user(41)
        await premium.activate(41, 7, 1)
        self.assertTrue(await premium.revoke(41))
        self.assertFalse((await premium.status(41))["active"])


class TestReferrals(Base):
    async def test_tracking_and_single_reward(self):
        a = await self.new_user(50)
        code = await referrals.ensure_code(50)
        self.assertEqual(code, await referrals.ensure_code(50))
        await self.new_user(51)
        r = await referrals.track(51, code)
        self.assertEqual((r.status, r.referrer_id), ("ok", 50))
        self.assertEqual((await users.get(51))["referred_by"], 50)
        self.assertEqual((await referrals.stats(50))["pending"], 1)
        reward = await referrals.reward_on_verify(51)
        self.assertEqual(reward, {"referrer_id": 50, "quota": 2, "days": 0, "mode": "total"})
        self.assertIsNone(await referrals.reward_on_verify(51))      # never twice
        doc = await users.get(50)
        self.assertEqual((doc["quota_remaining"], doc["referral_count"]), (7, 1))
        self.assertEqual((await referrals.stats(50))["rewarded"], 1)

    async def test_abuse_protection(self):
        await self.new_user(60)
        code = await referrals.ensure_code(60)
        self.assertEqual((await referrals.track(60, code)).status, "self")
        self.assertEqual((await referrals.track(61, "bogus")).status, "invalid_code")
        await self.new_user(61)
        self.assertEqual((await referrals.track(61, code)).status, "ok")
        self.assertEqual((await referrals.track(61, code)).status, "already_referred")
        await settings.set("referral_daily_cap", 2)
        await self.new_user(62)
        self.assertEqual((await referrals.track(62, code)).status, "ok")
        await self.new_user(63)
        self.assertEqual((await referrals.track(63, code)).status, "cap_reached")
        await users.ban(60, "x")
        await self.new_user(64)
        self.assertEqual((await referrals.track(64, code)).status, "referrer_banned")
        await settings.set("referral_enabled", False)
        self.assertEqual((await referrals.track(64, code)).status, "disabled")

    async def test_reward_config_and_premium_days(self):
        await self.new_user(70)
        code = await referrals.ensure_code(70)
        await settings.set("referral_reward_quota", 0)
        await settings.set("referral_reward_premium_days", 3)
        await self.new_user(71)
        await referrals.track(71, code)
        await referrals.reward_on_verify(71)
        self.assertTrue((await premium.status(70))["active"])
        self.assertEqual((await users.get(70))["quota_remaining"], 5)


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


class TestForceSubscribe(Base):
    async def test_evaluate_missing_unknown_and_errors(self):
        chs = [{"chat_id": 1}, {"chat_id": 2}, {"chat_id": 3}, {"chat_id": 4}]

        async def checker(ch, uid):
            if ch["chat_id"] == 3:
                return None
            if ch["chat_id"] == 4:
                raise RuntimeError("boom")
            return ch["chat_id"] == 1
        res = await evaluate(5, chs, checker)
        self.assertEqual([c["chat_id"] for c in res.missing], [2])
        self.assertEqual([c["chat_id"] for c in res.unknown], [3, 4])
        self.assertTrue(res.blocked)
        ok = await evaluate(5, chs[:1], checker)
        self.assertFalse(ok.blocked)
        self.assertFalse((await evaluate(5, [], checker)).blocked)

    async def test_channel_storage_public_and_private(self):
        self.assertTrue(await channels.add("fsub", -1001, "Pub", "pubchan"))
        self.assertTrue(await channels.add("fsub", -1002, "Priv", None, "https://t.me/+abc", True))
        self.assertFalse(await channels.add("fsub", -1001, "Pub renamed", "pubchan"))      # upsert
        rows = await channels.list_role("fsub")
        self.assertEqual([channels.join_url(c) for c in rows], ["https://t.me/pubchan", "https://t.me/+abc"])
        await channels.set_invite("fsub", -1001, "https://t.me/+zzz")
        self.assertEqual(channels.join_url(await channels.get("fsub", -1001)), "https://t.me/+zzz")
        self.assertEqual(await channels.list_role("source"), [])
        self.assertTrue(await channels.remove("fsub", -1002))
        await settings.set("forcesub_enabled", True)
        self.assertTrue(await settings.get("forcesub_enabled"))


class TestAdminsAndBroadcast(Base):
    async def test_admin_permissions(self):
        self.assertTrue(await admins.is_admin(1))
        self.assertTrue(await admins.has_perm(1, "broadcast"))
        self.assertTrue(await admins.has_perm(1, admins.OWNER_ONLY))
        self.assertFalse(await admins.is_admin(900))
        self.assertTrue(await admins.add(900, 1))
        self.assertFalse(await admins.add(900, 1))
        self.assertTrue(await admins.has_perm(900, "users"))
        self.assertFalse(await admins.has_perm(900, "broadcast"))
        self.assertFalse(await admins.has_perm(900, admins.OWNER_ONLY))
        self.assertTrue(await admins.toggle_perm(900, "broadcast"))
        self.assertTrue(await admins.has_perm(900, "broadcast"))
        self.assertFalse(await admins.toggle_perm(900, "broadcast"))
        self.assertIsNone(await admins.toggle_perm(900, "bogus"))
        self.assertFalse(await admins.has_perm(12345, "users"))
        self.assertTrue(await admins.remove(900))
        self.assertFalse(await admins.is_admin(900))

    async def test_broadcast_permissions_audience_and_run(self):
        for i in range(100, 110):
            await self.new_user(i)
        await users.ban(100, "x")
        await premium.activate(101, 7, 1)
        await users.mark_blocked(102)
        await admins.add(901, 1, ["users"])
        with self.assertRaises(PermissionError):
            await broadcast.launch(901, "all", 1, 1)                      # admin without permission
        with self.assertRaises(PermissionError):
            await broadcast.launch(555, "all", 1, 1)                      # ordinary user
        await admins.toggle_perm(901, "broadcast")
        doc, ids = await broadcast.launch(901, "all", 1, 1)
        self.assertEqual(sorted(ids), [101] + list(range(103, 110)))     # banned & blocked excluded
        self.assertEqual((await users.audience("premium")), [101])
        self.assertEqual(len(await users.audience("free")), 7)

        async def send(uid):
            return {103: "blocked", 104: "failed"}.get(uid, "ok")
        self.assertIsNotNone(await __import__("database.broadcasts", fromlist=["x"]).claim_start(doc["_id"]))
        self.assertIsNone(await __import__("database.broadcasts", fromlist=["x"]).claim_start(doc["_id"]))
        progress = []

        async def on_progress(*a):
            progress.append(a)
        rep = await broadcast.run(doc["_id"], ids, send, on_progress, delay=0, progress_every=3)
        self.assertEqual((rep["sent"], rep["blocked"], rep["failed"], rep["status"]), (6, 1, 1, "done"))
        self.assertTrue(progress)
        self.assertTrue((await users.get(103))["blocked"])

    async def test_broadcast_cancel(self):
        for i in range(200, 205):
            await self.new_user(i)
        doc, ids = await broadcast.launch(1, "all", 1, 1)

        async def send(uid):
            if uid == 201:
                broadcast.cancel(doc["_id"])
            return "ok"
        rep = await broadcast.run(doc["_id"], sorted(ids), send, delay=0)
        self.assertEqual(rep["status"], "cancelled")
        self.assertLess(rep["sent"], 5)


class TestRequestsAndLogs(Base):
    async def test_requests_flow_and_limit(self):
        for _ in range(3):
            d, why = await requests.create(80, "Some movie")
            self.assertEqual(why, "ok")
        self.assertEqual((await requests.create(80, "x"))[1], "limit")
        self.assertEqual(await requests.count("pending"), 3)
        rid = (await requests.list_status("pending"))[0]["_id"]
        self.assertEqual((await requests.decide(rid, "approved", 1))["status"], "approved")
        self.assertIsNone(await requests.decide(rid, "rejected", 1))
        auto, _ = await requests.create(81, "auto", auto_approve=True)
        self.assertEqual(auto["status"], "approved")


class TestRateLimiter(unittest.TestCase):
    def test_window_strikes_and_mute(self):
        rl = SlidingWindowLimiter()
        res = [rl.hit(1, 3, 10, now=t) for t in (0, 1, 2, 3)]
        self.assertEqual([r[0] for r in res], [True, True, True, False])
        self.assertTrue(rl.hit(1, 3, 10, now=11)[0])
        self.assertFalse(rl.strike(1, 3, 60, now=0))
        self.assertFalse(rl.strike(1, 3, 60, now=1))
        self.assertTrue(rl.strike(1, 3, 60, now=2))
        self.assertGreater(rl.muted_for(1, now=3), 50)
        self.assertEqual(rl.muted_for(1, now=100), 0)
        self.assertTrue(rl.notify_due(1, 10, now=0))
        self.assertFalse(rl.notify_due(1, 10, now=5))


class TestPersistence(unittest.IsolatedAsyncioTestCase):
    async def test_settings_and_data_survive_restart(self):
        if helpers.USING_REAL_MONGO or os.getenv("TEST_MONGO_URI"):
            self.skipTest("file-based restart simulation only applies to the in-memory emulator")
        path = os.path.join(tempfile.mkdtemp(), "db.pkl")
        db = helpers.FakeDB(path)
        mongo.use(db)
        settings.clear_cache()
        await mongo.ensure_indexes()
        await settings.set("free_quota", 8)
        await settings.update_in("links", "main_channel", "https://t.me/persisted")
        await users.register(7, "Persist", "p_user")
        await premium.activate(7, 30, 1)
        db.save()
        # "restart": new process = empty caches, new database object loaded from disk
        db2 = helpers.FakeDB(path)
        mongo.use(db2)
        settings.clear_cache()
        self.assertEqual(await settings.get("free_quota"), 8)
        self.assertEqual((await settings.get("links"))["main_channel"], "https://t.me/persisted")
        doc = await users.get(7)
        self.assertEqual(doc["first_name"], "Persist")
        self.assertTrue((await premium.status(7))["active"])
        self.assertEqual(await settings.get("sharing_enabled"), True)       # default for untouched keys


if __name__ == "__main__":
    unittest.main()


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


class TestButtonSettingsPersist(Base):
    async def test_buttons_stored_in_db(self):
        from utils.buttons import merge
        await settings.set("channel_buttons", merge([], [{"text": "Main", "url": "https://t.me/mainch"}])[0])
        settings.clear_cache()
        self.assertEqual((await settings.get("channel_buttons"))[0]["text"], "Main")
        self.assertFalse(await settings.get("buttons_enabled"))


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


class TestDailyLimit(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await settings.set("quota_mode", "daily")
        await settings.set("day_reset_offset_min", 0)

    def at(self, days=0, hours=0):
        from unittest import mock
        base = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
        return mock.patch("database.users.utcnow", lambda: base + timedelta(days=days, hours=hours))

    async def test_two_files_per_day_then_blocked(self):
        await self.new_user(300)
        toks = await self.approved_files(4)
        res = [await sharing.share_file(300, t) for t in toks]
        self.assertEqual([r.ok for r in res], [True, True, False, False])
        self.assertEqual({r.reason for r in res[2:]}, {"limit"})
        doc = await users.get(300)
        self.assertEqual((doc["daily_left"], doc["daily_limit_eff"], doc["quota_display"]), (0, 2, "0/2 today"))

    async def test_limit_refills_next_day(self):
        await self.new_user(301)
        toks = await self.approved_files(6)
        with self.at(0):
            self.assertEqual([(await sharing.share_file(301, t)).ok for t in toks[:3]], [True, True, False])
        with self.at(1):
            self.assertEqual((await users.get(301))["daily_left"], 2)
            self.assertEqual([(await sharing.share_file(301, t)).ok for t in toks[2:5]], [True, True, False])

    async def test_reset_time_follows_timezone_offset(self):
        await settings.set("day_reset_offset_min", 330)       # IST: new day starts 18:30 UTC
        await self.new_user(302)
        toks = await self.approved_files(5)
        with self.at(0, hours=5):                               # 17:00 UTC = 22:30 IST
            self.assertEqual([(await sharing.share_file(302, t)).ok for t in toks[:3]], [True, True, False])
        with self.at(0, hours=7):                               # 19:00 UTC = 00:30 IST next day
            self.assertTrue((await sharing.share_file(302, toks[2])).ok)

    async def test_referral_raises_daily_limit_permanently(self):
        await self.new_user(303)
        code = await referrals.ensure_code(303)
        toks = await self.approved_files(8)
        with self.at(0):
            await sharing.share_file(303, toks[0]); await sharing.share_file(303, toks[1])
            self.assertEqual((await sharing.share_file(303, toks[2])).reason, "limit")
            await self.new_user(304)
            await referrals.track(304, code)
            reward = await referrals.reward_on_verify(304)
            self.assertEqual((reward["quota"], reward["mode"]), (2, "daily"))
            doc = await users.get(303)
            self.assertEqual((doc["daily_limit_eff"], doc["daily_left"], doc["bonus_limit"]), (4, 2, 2))
            self.assertEqual([(await sharing.share_file(303, t)).ok for t in toks[2:5]], [True, True, False])
        with self.at(1):                                        # tomorrow the base 2 + 2 bonus = 4 again
            self.assertEqual((await users.get(303))["daily_left"], 4)
            self.assertEqual([(await sharing.share_file(303, t)).ok for t in toks[4:8]], [True] * 4)
            self.assertEqual((await users.get(303))["daily_left"], 0)

    async def test_concurrent_requests_respect_daily_limit_even_on_rollover(self):
        await self.new_user(305)
        toks = await self.approved_files(30)
        res = await asyncio.gather(*(sharing.share_file(305, t) for t in toks))
        self.assertEqual(sum(r.ok for r in res), 2)
        self.assertEqual(await sharing.count(305), 2)
        with self.at(1):
            res = await asyncio.gather(*(sharing.share_file(305, t) for t in toks))
            self.assertEqual(sum(r.ok for r in res if r.reason == "ok"), 2)   # 2 new shares tomorrow (older ones are 'already')

    async def test_premium_unlimited_and_admin_controls(self):
        await self.new_user(306)
        await premium.activate(306, 7, 1)
        toks = await self.approved_files(6)
        self.assertTrue(all([(await sharing.share_file(306, t)).ok for t in toks]))
        await self.new_user(307)
        t2 = await self.approved_files(5, start=50)
        await users.set_quota(307, 3)                           # admin: custom daily limit for this user
        self.assertEqual([(await sharing.share_file(307, t)).ok for t in t2[:4]], [True, True, True, False])
        self.assertEqual(await users.reset_quota(307), 2)       # reset: override removed, allowance refilled
        self.assertEqual((await users.get(307))["daily_left"], 2)
        await users.set_unlimited(307, True)
        self.assertTrue((await sharing.share_file(307, t2[4])).ok)

    async def test_mode_default_and_banned_user(self):
        settings.clear_cache()
        db_default = __import__("database.settings", fromlist=["x"]).DEFAULTS
        self.assertEqual((db_default["quota_mode"], db_default["daily_limit"], db_default["protect_content"]), ("daily", 2, False))
        await self.new_user(308)
        await users.ban(308, "x")
        (t,) = await self.approved_files(1)
        self.assertEqual((await sharing.share_file(308, t)).reason, "banned")


class FakeClient:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def get_me(self):
        from types import SimpleNamespace
        return SimpleNamespace(username="testbot")

    async def send_cached_media(self, chat_id, file_id, **kw):
        if self.fail:
            from pyrogram.errors import RPCError
            raise RPCError("boom")
        self.sent.append((chat_id, file_id, kw))


class TestDelivery(Base):
    """The daily limit counts files a user RECEIVES (a copy they can save/forward)."""
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await settings.set("quota_mode", "daily")

    async def test_two_files_per_day_via_delivery(self):
        from utils import delivery
        await self.new_user(400)
        toks = await self.approved_files(4)
        client = FakeClient()
        res = [await delivery.deliver(client, await users.get(400), t) for t in toks]
        self.assertEqual(res, ["ok", "ok", "limit", "limit"])
        self.assertEqual(len(client.sent), 2)
        self.assertEqual(await delivery.deliver(client, await users.get(400), toks[0]), "ok")   # already has it: free
        self.assertEqual(len(client.sent), 3)
        doc = await users.get(400)
        txt = await delivery.reason_text("en", "limit", doc)
        self.assertIn("2", txt)
        self.assertIn("+2", txt)

    async def test_referral_adds_two_more_files(self):
        from utils import delivery
        await self.new_user(401)
        code = await referrals.ensure_code(401)
        toks = await self.approved_files(5)
        client = FakeClient()
        for t in toks[:2]:
            await delivery.deliver(client, await users.get(401), t)
        self.assertEqual(await delivery.deliver(client, await users.get(401), toks[2]), "limit")
        await self.new_user(402)
        await referrals.track(402, code)
        await referrals.reward_on_verify(402)
        res = [await delivery.deliver(client, await users.get(401), t) for t in toks[2:5]]
        self.assertEqual(res, ["ok", "ok", "limit"])

    async def test_failed_send_does_not_cost_a_file(self):
        from utils import delivery
        await self.new_user(403)
        (t,) = await self.approved_files(1)
        self.assertEqual(await delivery.deliver(FakeClient(fail=True), await users.get(403), t), "unavailable")
        self.assertEqual((await users.get(403))["daily_left"], 2)
        self.assertEqual(await sharing.count(403), 0)
        self.assertEqual(await delivery.deliver(FakeClient(), await users.get(403), t), "ok")

    async def test_admin_premium_banned_and_access_rules(self):
        from utils import delivery
        toks = await self.approved_files(5)
        client = FakeClient()
        await self.new_user(404)
        self.assertTrue(all([await delivery.deliver(client, await users.get(404), t, is_admin=True) == "ok" for t in toks]))
        self.assertEqual((await users.get(404))["daily_left"], 2)           # admins never spend the allowance
        await self.new_user(405)
        await premium.activate(405, 7, 1)
        self.assertTrue(all([await delivery.deliver(client, await users.get(405), t) == "ok" for t in toks]))
        await self.new_user(406)
        await users.ban(406, "x")
        self.assertEqual(await delivery.deliver(client, await users.get(406), toks[0]), "banned")
        await files.set_visibility(toks[1], "premium")
        await self.new_user(407)
        self.assertEqual(await delivery.deliver(client, await users.get(407), toks[1]), "premium_only")
        pending, _ = await files.submit(407, media(90))
        self.assertEqual(await delivery.deliver(client, await users.get(407), pending["_id"]), "pending")

    async def test_roaroic_caption_design(self):
        from utils import captioning
        out = await captioning.compute_caption("Movie 2026 1080p", "Movie.mkv")
        self.assertIn("Movie 2026 1080p", out)
        self.assertTrue(out.startswith("<b>[ @roaroic0 ]</b> Movie 2026 1080p"))
        self.assertEqual(out.count(captions.DIVIDER), 2)
        for url in captions.ROAROIC_LINKS.values():
            self.assertIn(url, out)
        self.assertTrue(out.endswith("ROAROIC MOVIE'S || 0.1</b> 💫"))
        self.assertLessEqual(captions.visible_len(out), 1024)
        again = await captioning.compute_caption(out, "Movie.mkv")     # re-editing must not stack footers
        self.assertEqual(again, out)

    async def test_design_seed_overrides_old_links_once(self):
        await settings.set("links", {"main_channel": "https://t.me/roaroic0", "x": "https://t.me/old1"})
        await settings.set("active_template", "quote")
        self.assertTrue(await settings.seed_roaroic())
        self.assertEqual(await settings.get("links"), captions.ROAROIC_LINKS)
        self.assertEqual(await settings.get("active_template"), "roaroic")
        self.assertIn("https://t.me/old1", await settings.get("old_links"))
        self.assertFalse(await settings.seed_roaroic())              # second start: admin edits are kept
        await settings.set("active_template", "minimal")
        self.assertFalse(await settings.seed_roaroic())
        self.assertEqual(await settings.get("active_template"), "minimal")

    async def test_invite_link_under_every_file(self):
        from utils import delivery
        await self.new_user(420)
        toks = await self.approved_files(2)
        client = FakeClient()
        for t in toks:
            await delivery.deliver(client, await users.get(420), t)
        code = await referrals.ensure_code(420)
        for _, _, kw in client.sent:
            self.assertIn(f"https://t.me/testbot?start=r_{code}", kw["caption"])
            self.assertLessEqual(len(kw["caption"]), 1024)
            self.assertIsNotNone(kw["reply_markup"])
        long = delivery.build_caption("x" * 2000, "\n\nFOOT")
        self.assertTrue(long.endswith("FOOT") and len(long) <= 1024)

    async def test_protect_content_flag_and_sharing_switch(self):
        from utils import delivery
        await self.new_user(408)
        toks = await self.approved_files(2)
        client = FakeClient()
        await delivery.deliver(client, await users.get(408), toks[0])
        self.assertFalse(client.sent[-1][2]["protect_content"])             # default: user may save/forward (counted)
        await settings.set("protect_content", True)
        await delivery.deliver(client, await users.get(408), toks[1])
        self.assertTrue(client.sent[-1][2]["protect_content"])
        await settings.set("sharing_enabled", False)
        t3 = (await self.approved_files(1, start=70))[0]
        for t in (toks[0], t3):                                              # admin kill switch stops every delivery
            self.assertEqual(await delivery.deliver(client, await users.get(408), t), "disabled")
        self.assertEqual(await delivery.deliver(client, await users.get(408), t3, is_admin=True), "ok")

    async def test_concurrent_deliveries_never_exceed_limit(self):
        from utils import delivery
        await self.new_user(409)
        toks = await self.approved_files(20)
        client = FakeClient()
        doc = await users.get(409)
        res = await asyncio.gather(*(delivery.deliver(client, doc, t) for t in toks))
        self.assertEqual(res.count("ok"), 2)
        self.assertEqual(len(client.sent), 2)
