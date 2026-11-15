# ROAROIC AUTO LINK BOT

Telegram file-sharing bot with share quotas, premium plans, referrals, an automatic channel caption editor,
force-subscribe, broadcast and a full inline admin panel. Developer: **@roaroic0**.
Stack: Python 3.11, Pyrogram API (Kurigram fork), MongoDB Atlas (Motor), aiohttp health endpoint, Render.

## Architecture choice
**Pyrogram (MTProto) instead of the plain Bot API.** Reasons: it receives *channel posts* and can edit their captions
(core feature), handles `FloodWait` explicitly, uses `file_id`s directly, and runs fully async. The original
`pyrogram==2.0.106` is unmaintained and fails on newer channel IDs, so `requirements.txt` uses **Kurigram**, a maintained
drop-in fork (`import pyrogram` unchanged). Trade-off: needs `API_ID`/`API_HASH` in addition to the bot token.

```
bot.py            entry: Mongo -> health server -> Pyrogram -> background workers -> graceful shutdown
config.py         environment variables only
database/         mongo.py (connect+indexes) users files sharing premium referrals settings admins channels requests logs broadcasts
plugins/          Telegram handlers: middleware callbacks inputs start sharing filters(search) captions premium referrals
                  requests broadcast admin admin_settings admin_system
keyboards/        inline keyboard builders
utils/            captions (pure), forcesub, ratelimit, broadcast engine, router, i18n (EN/HI), logger (redaction), health, backup, workers, tg helpers
tests/            test_core.py (logic + DB), test_smoke.py (structure of the Telegram layer), fake_mongo.py
```
Business logic lives in `database/` and `utils/` (no Telegram imports) so it is unit-testable; `plugins/` stays thin.

## Interpretation of "file share"
A **share** = a user creating a share link (`t.me/<bot>?start=f_<token>`) for an approved file (their own approved
submission, a search result, or a channel-indexed file). The **first** link for a given file costs one permission;
re-opening the same file's link is free (unique index `(user, file)`), so users are never charged twice. Recipients open
the link and receive the file (force-subscribe, ban and premium-only rules apply) without spending anything.
Quota consumption is a single conditional `update_one` on the user document, i.e. atomic in MongoDB.

Deliberately **not implemented** (as requested): custom file expiry, one-time download links, download counter.
(Nothing records or counts file downloads; share history records link creation only.)

## Setup (local)
1. Create a bot with @BotFather. Get `API_ID`/`API_HASH` at https://my.telegram.org.
2. Create a free MongoDB Atlas cluster, a database user, and allow network access (`0.0.0.0/0` for Render, or Render's outbound IPs).
3. `python3.11 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
4. `cp .env.example .env` and fill it in. `python bot.py`
5. Add the bot as **admin** (with *Edit messages* for caption editing; *Invite users* helps for private force-sub channels) to your channels,
   then open `/admin` in the bot -> *Channel Settings* / *Force Subscribe*.

## Environment variables
| Variable | Required | Meaning |
|---|---|---|
| `API_ID`, `API_HASH` | yes | Telegram app credentials |
| `BOT_TOKEN` | yes | BotFather token |
| `MONGO_URI` | yes | Atlas connection string |
| `OWNER_ID` | yes | Owner Telegram ID(s), comma separated. Owners hold every permission |
| `DB_NAME` | no | default `roaroic_autolink` |
| `PORT` | no | health server port (Render sets it) |
| `LOG_LEVEL` | no | default `INFO` |
All other settings (quota, links, templates, force-sub, referral rewards...) are stored in MongoDB and edited in the admin panel.

## Deploy on Render
1. Push this folder to GitHub. Render -> *New* -> *Blueprint* -> select the repo (uses `render.yaml`), or create a *Web Service* manually:
   build `pip install -r requirements.txt`, start `python bot.py`, health check path `/health`.
2. Fill the secret env vars (`sync: false` ones). 3. Deploy and watch the logs for "started as @yourbot".

### Render limitations (read before relying on it)
* The **free web service spins down after ~15 minutes without inbound HTTP traffic**, which takes the bot offline;
  free instances also restart at least daily and have a monthly hour allowance. External pingers only partly help and are not a guarantee.
* Render offers background workers only on paid plans; this project exposes `/health` so it can run as a web service.
* The filesystem is ephemeral: nothing important is stored on disk (sessions are in-memory, data is in MongoDB).
* On deploy/restart Render sends SIGTERM; the bot shuts down gracefully (tasks cancelled, Telegram client and MongoDB closed).
* Use a paid instance (render.yaml defaults to `starter`) for continuous operation. I have **not** deployed this; treat the first deploy as unverified.

## Telegram limitations and how they are handled
* Captions are limited to 1024 characters: long originals are truncated (footer always kept, UTF-16 aware).
* A bot can only verify channel membership where it is an **admin**: adding a force-sub channel is refused otherwise.
  Join-request invite links cannot be verified until the user is approved. If Telegram cannot answer for a channel, the check fails open and logs a warning.
* Bots can't message users who never started them; blocked users are flagged and skipped in broadcasts.
* `file_id`s only work for the bot that received them: files must be sent to this bot (or posted in a channel it is in).
* Backups are sent as Telegram documents (50 MB bot limit): split per collection if larger. Restore is manual (`mongoimport`).

## Admin quick reference
`/admin` opens the panel. Commands: `/ban id [reason]`, `/unban id`, `/broadcast [audience]` (reply to a message).
Owners manage admins; each admin gets per-section permissions (`users files sharing premium referrals captions channels forcesub broadcast stats security maintenance backup logs system`).
Caption template placeholders: `{original_caption} {main_channel} {backup_channel} {movie_bot} {discussion_group}`; lines with an unset link are dropped.

## Tests
`python -m unittest discover -s tests -t .` (no pytest needed). Set `TEST_MONGO_URI` (and install `motor`) to run the same logic tests against a real MongoDB instead of the bundled in-memory emulator.
