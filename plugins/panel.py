"""Owner control panel: everything is done with inline buttons (menus) plus short typed steps
(link names, button text, ranges...). Menu screens are built in utils/ui.py."""
import io
import logging

from pyrogram import Client, filters

import config
from utils import inputs, jobs, pending, runner, store, templates, tg, ui
from utils.buttons import merge, parse_lines
from utils.captioning import compute_caption
from utils.captions import normalize_url, validate_template, validate_url
from utils.oldposts import parse_range

log = logging.getLogger(__name__)
owner = filters.user(list(config.OWNER_IDS)) if config.OWNER_IDS else filters.user([0])
D = store.DEFAULT


# ---- sending screens --------------------------------------------------------------------------------------
async def show(cq, screen) -> None:
    from pyrogram.errors import MessageNotModified
    text, rows = screen
    try:
        await cq.message.edit_text(text, reply_markup=tg.menu_markup(rows), **tg.nopreview(cq.message.edit_text))
    except MessageNotModified:
        pass


async def reply(message, screen, note: str = "") -> None:
    text, rows = screen
    await message.reply_text((note + "\n\n" if note else "") + text, reply_markup=tg.menu_markup(rows),
                             **tg.nopreview(message.reply_text))


# ---- commands ---------------------------------------------------------------------------------------------
@Client.on_message(filters.command(["start", "menu"]) & filters.private & owner)
async def menu_cmd(client, message):
    pending.clear(message.from_user.id)
    await reply(message, ui.main_screen())


@Client.on_message(filters.command("cancel") & filters.private & owner)
async def cancel_cmd(client, message):
    pending.clear(message.from_user.id)
    await reply(message, ui.main_screen(), "❎ Cancelled.")


@Client.on_message(filters.command("backup") & filters.private & owner)
async def backup_cmd(client, message):
    await _send_backup(client, message.chat.id)


@Client.on_message(filters.command("restore") & filters.private & owner)
async def restore_cmd(client, message):
    target = message.reply_to_message
    doc = getattr(target, "document", None)
    if not doc or (doc.file_size or 0) > 1_000_000:
        await message.reply_text("↩️ Reply to a settings backup file (.json) with /restore.")
        return
    buf = await client.download_media(target, in_memory=True)
    ok, msg = store.import_json(buf.getvalue())
    await reply(message, ui.main_screen(), ("✅ " if ok else "❌ ") + msg)


async def _send_backup(client, chat_id) -> None:
    f = io.BytesIO(store.export_json())
    f.name = "roaroic-settings.json"
    await client.send_document(chat_id, f, caption="💾 Settings backup.\nTo restore: reply to this file with /restore")


# ---- button taps ------------------------------------------------------------------------------------------
async def h_main(client, cq):
    return ui.main_screen()


async def h_noop(client, cq):
    return None


async def h_help(client, cq):
    return ui.help_screen()


async def h_cancel(client, cq, scope="m"):
    return ui.main_screen() if scope == "m" else ui.channel_screen(scope)


async def h_chs(client, cq, page="0"):
    return ui.channels_screen(int(page))


async def h_ch(client, cq, scope):
    return ui.channel_screen(scope)


async def h_add(client, cq):
    pending.put(cq.from_user.id, "addch")
    return ui.prompt_screen("➕ <b>Add channel</b>\n\nForward <b>any post</b> from the channel here, or send its "
                            "ID / @username / link.\n\n⚠️ I must already be <b>admin</b> there "
                            "(with <i>Edit messages</i> right).")


async def h_rc(client, cq, scope):
    return ui.confirm_remove_screen(scope)


async def h_rmy(client, cq, scope):
    store.delete_channel(scope)
    return ui.channels_screen(0), "🗑 Removed"


async def h_tg(client, cq, scope, what):
    c = store.get(scope)
    if c is None or store.key(scope) == D:
        return ui.missing()
    field = "caption" if what == "cap" else "buttons_on"
    store.update(scope, **{field: not c[field]})
    now = store.get(scope)[field]
    return (ui.buttons_screen(scope) if what == "btnb" else ui.channel_screen(scope)), \
        f"{'Caption' if what == 'cap' else 'Buttons'}: {'ON' if now else 'OFF'}"


# template
async def h_tpl(client, cq, scope):
    return ui.template_screen(scope)


async def h_tps(client, cq, scope, key):
    if key == "inherit" and store.key(scope) != D:
        store.update(scope, template=None)
    elif key in templates.PRESETS:
        store.update(scope, template=key)
    else:
        return ui.template_screen(scope)
    return ui.template_screen(scope), "Saved ✅"


async def h_tpc(client, cq, scope):
    pending.put(cq.from_user.id, "tpl_custom", scope=scope)
    return ui.custom_template_prompt(scope)


# links
async def h_lk(client, cq, scope):
    return ui.links_screen(scope)


async def h_lka(client, cq, scope):
    pending.put(cq.from_user.id, "link_add", scope=scope)
    return ui.link_add_prompt(scope)


async def h_lki(client, cq, scope, name):
    return ui.link_screen(scope, name)


async def h_lke(client, cq, scope, name):
    pending.put(cq.from_user.id, "link_url", scope=scope, name=name)
    return ui.prompt_screen(f"✏️ Send the new URL for <b>{ui.esc(ui.label(name))}</b>\nExample: <code>https://t.me/yourchannel</code> "
                            "or <code>@yourchannel</code>", scope)


async def h_lkd(client, cq, scope, name):
    store.del_link(scope, name)
    return ui.links_screen(scope), "Deleted"


async def h_lkr(client, cq, scope):
    store.reset_links(scope)
    return ui.links_screen(scope), "Using default links"


# old links
async def h_ol(client, cq, scope):
    return ui.oldlinks_screen(scope)


async def h_ola(client, cq, scope):
    pending.put(cq.from_user.id, "old_add", scope=scope)
    return ui.oldlinks_add_prompt(scope)


async def h_olc(client, cq, scope):
    store.clear_old_links(scope)
    return ui.oldlinks_screen(scope), "Cleared"


# buttons
async def h_bt(client, cq, scope):
    return ui.buttons_screen(scope)


async def h_bta(client, cq, scope):
    pending.put(cq.from_user.id, "btn_text", scope=scope)
    return ui.button_add_prompt(1, scope)


async def h_btm(client, cq, scope):
    pending.put(cq.from_user.id, "btn_many", scope=scope)
    return ui.buttons_many_prompt(scope)


async def h_bti(client, cq, scope, idx):
    return ui.button_screen(scope, int(idx))


async def h_bte(client, cq, scope, idx, what):
    pending.put(cq.from_user.id, "btn_edit", scope=scope, idx=int(idx), what=what)
    return ui.button_edit_prompt(scope, int(idx), what)


async def _move(scope, idx, step):
    btns, i = store.buttons(scope), int(idx)
    j = i + step
    if 0 <= i < len(btns) and 0 <= j < len(btns):
        btns[i], btns[j] = btns[j], btns[i]
        store.set_buttons(scope, btns)
        return ui.button_screen(scope, j)
    return ui.button_screen(scope, i)


async def h_btu(client, cq, scope, idx):
    return await _move(scope, idx, -1)


async def h_btd(client, cq, scope, idx):
    return await _move(scope, idx, +1)


async def h_btx(client, cq, scope, idx):
    btns, i = store.buttons(scope), int(idx)
    if 0 <= i < len(btns):
        del btns[i]
        store.set_buttons(scope, btns)
    return ui.buttons_screen(scope), "Deleted"


async def h_btr(client, cq, scope, n):
    store.update(scope, per_row=2 if n == "2" else 1)
    return ui.buttons_screen(scope), "Saved ✅"


async def h_btc(client, cq, scope):
    return ui.confirm_clear_buttons(scope)


async def h_btcy(client, cq, scope):
    store.set_buttons(scope, [])
    return ui.buttons_screen(scope), "Cleared"


# run on old posts
async def h_run(client, cq, scope):
    return ui.run_screen(scope)


async def h_rm(client, cq, scope, mode):
    if mode not in runner.MODES:
        return ui.run_screen(scope)
    if jobs.busy():
        return ui.run_screen(scope), "!A job is already running. Stop it first."
    if mode == "buttons" and not store.buttons(scope):
        return ui.run_screen(scope), "!This channel has no buttons yet. Add some in 🔘 Manage buttons."
    pending.put(cq.from_user.id, "run_range", scope=scope, mode=mode)
    return ui.run_range_prompt(scope, mode)


async def h_stop(client, cq):
    jobs.request_stop()
    return None, "Stopping after the current post…"


# preview / backup
async def h_pv(client, cq, scope):
    k = store.key(scope)
    text = compute_caption("Sample Movie (2024) 1080p WEB-DL", None, None if k == D else k)
    e = store.effective(k)
    mk = tg.url_markup(e["buttons"], e["per_row"]) if k != D else None
    await client.send_message(cq.message.chat.id, text, reply_markup=mk, **tg.nopreview(client.send_message))
    return None, "Preview sent 👇"


async def h_bk(client, cq):
    await _send_backup(client, cq.message.chat.id)
    return None, "Backup sent 👇"


HANDLERS = {
    "m": h_main, "noop": h_noop, "help": h_help, "x": h_cancel, "chs": h_chs, "ch": h_ch, "add": h_add,
    "rc": h_rc, "rmy": h_rmy, "tg": h_tg, "tpl": h_tpl, "tps": h_tps, "tpc": h_tpc,
    "lk": h_lk, "lka": h_lka, "lki": h_lki, "lke": h_lke, "lkd": h_lkd, "lkr": h_lkr,
    "ol": h_ol, "ola": h_ola, "olc": h_olc,
    "bt": h_bt, "bta": h_bta, "btm": h_btm, "bti": h_bti, "bte": h_bte, "btu": h_btu, "btd": h_btd,
    "btx": h_btx, "btr": h_btr, "btc": h_btc, "btcy": h_btcy,
    "run": h_run, "rm": h_rm, "stop": h_stop, "pv": h_pv, "bk": h_bk,
}


def split_result(res):
    """Handlers return a screen, None, or (screen|None, toast). A screen is (text, rows)."""
    if isinstance(res, tuple) and len(res) == 2 and isinstance(res[1], str):
        return res
    return res, None


@Client.on_callback_query(owner)
async def on_callback(client, cq):
    parts = (cq.data or "").split(":")
    handler = HANDLERS.get(parts[0])
    if handler is None or cq.message is None:
        await cq.answer()
        return
    if parts[0] not in ("noop", "stop"):
        pending.clear(cq.from_user.id)              # a new menu tap cancels any half-finished typed step
    screen = toast = None
    try:
        screen, toast = split_result(await handler(client, cq, *parts[1:]))
        if screen:
            await show(cq, screen)
    except Exception:
        log.exception("menu action %s failed", cq.data)
        toast = "!Something went wrong. Try again or /menu."
    try:
        if toast and toast.startswith("!"):
            await cq.answer(toast[1:], show_alert=True)
        else:
            await cq.answer(toast or "")
    except Exception:
        pass


# ---- typed steps ------------------------------------------------------------------------------------------
async def _has_pending(_, __, message):
    return bool(message.from_user) and pending.get(message.from_user.id) is not None


has_pending = filters.create(_has_pending, "has_pending")


def _type_name(chat) -> str:
    t = getattr(chat, "type", None)
    return str(getattr(t, "name", t)).upper().split(".")[-1]


async def _perm_line(client, chat_id) -> str:
    try:
        me = await client.get_chat_member(chat_id, "me")
    except Exception:
        return "⚠️ I could not check my admin rights. Make sure I am admin with <i>Edit messages</i>."
    status = str(getattr(getattr(me, "status", None), "name", getattr(me, "status", ""))).upper().split(".")[-1]
    if status == "OWNER":
        return "✅ I am the owner there."
    if status == "ADMINISTRATOR":
        priv = getattr(me, "privileges", None)
        if priv is not None and getattr(priv, "can_edit_messages", True) is False:
            return "⚠️ I am admin there, but without the <i>Edit messages</i> right."
        return "✅ I am admin there."
    return "⚠️ I am not admin there yet. Make me admin with the <i>Edit messages</i> right."


async def in_addch(client, message, st):
    chat = tg.forwarded_chat(message)
    ref = chat.id if chat else inputs.parse_channel_ref(message.text or "")
    if ref is None:
        return "retry", "❌ I could not understand that. Forward a post from the channel, or send its ID / @username / link."
    try:
        chat = await client.get_chat(ref)
    except Exception:
        return "retry", "❌ I can't open that chat. Make me admin there first, then send it again."
    if _type_name(chat) != "CHANNEL":
        return "retry", "❌ That is not a channel. Send a channel."
    _, created = store.ensure_channel(chat.id, chat.title)
    note = ("✅ Channel added.\n" if created else "ℹ️ It was already in the list.\n") + await _perm_line(client, chat.id)
    return "done", ui.channel_screen(str(chat.id)), note


async def in_link_add(client, message, st):
    key, url, err = inputs.parse_link_line(message.text or "")
    if err:
        return "retry", "❌ " + err
    err = store.set_link(st["scope"], key, url)
    if err:
        return "retry", "❌ " + err
    return "done", ui.links_screen(st["scope"]), f"✅ Saved <code>{key}</code>"


async def in_link_url(client, message, st):
    url = normalize_url(message.text or "")
    if not validate_url(url):
        return "retry", "❌ Send a valid link like https://t.me/yourchannel (or @yourchannel)."
    err = store.set_link(st["scope"], st["name"], url)
    if err:
        return "retry", "❌ " + err
    return "done", ui.link_screen(st["scope"], st["name"]), "✅ Saved"


async def in_tpl_custom(client, message, st):
    txt = (message.text or "").strip()
    ok, err = validate_template(txt, list(store.effective(st["scope"])["links"]))
    if not ok:
        return "retry", "❌ " + err
    store.update(st["scope"], template=templates.CUSTOM, custom_template=txt)
    return "done", ui.template_screen(st["scope"]), "✅ Custom template saved. Tap 👁 Preview to see it."


async def in_old_add(client, message, st):
    items = inputs.parse_old_links(message.text or "")
    if not items:
        return "retry", "❌ I found no link or @handle. Example: @oldchannel"
    n = store.add_old_links(st["scope"], items)
    return "done", ui.oldlinks_screen(st["scope"]), f"✅ Added {n}"


async def in_btn_text(client, message, st):
    text, err = inputs.parse_button_text(message.text or "")
    if err:
        return "retry", "❌ " + err
    pending.put(message.from_user.id, "btn_url", scope=st["scope"], text=text)
    return "next", ui.button_add_prompt(2, st["scope"])


async def in_btn_url(client, message, st):
    url = normalize_url(message.text or "")
    if not validate_url(url):
        return "retry", "❌ Send a valid link like https://t.me/yourchannel (or @yourchannel)."
    out, added, _ = merge(store.buttons(st["scope"]), [{"text": st["text"], "url": url}])
    if not added:
        return "done", ui.buttons_screen(st["scope"]), "⚠️ Not added — that link is already a button (or the limit is reached)."
    store.set_buttons(st["scope"], out)
    return "done", ui.buttons_screen(st["scope"]), "✅ Button added"


async def in_btn_many(client, message, st):
    ok, errors = parse_lines(message.text or "")
    if not ok:
        return "retry", "❌ Nothing valid found.\n" + "\n".join(errors[:5])
    out, added, skipped = merge(store.buttons(st["scope"]), ok)
    store.set_buttons(st["scope"], out)
    note = f"✅ Added {added}" + (f", skipped {skipped} (duplicate/limit)" if skipped else "")
    if errors:
        note += "\n⚠️ " + "\n⚠️ ".join(errors[:5])
    return "done", ui.buttons_screen(st["scope"]), note


async def in_btn_edit(client, message, st):
    btns, i = store.buttons(st["scope"]), st["idx"]
    if not 0 <= i < len(btns):
        return "done", ui.buttons_screen(st["scope"]), ""
    if st["what"] == "t":
        text, err = inputs.parse_button_text(message.text or "")
        if err:
            return "retry", "❌ " + err
        btns[i]["text"] = text
    else:
        url = normalize_url(message.text or "")
        if not validate_url(url):
            return "retry", "❌ Send a valid link like https://t.me/yourchannel (or @yourchannel)."
        btns[i]["url"] = url
    store.set_buttons(st["scope"], btns)
    return "done", ui.button_screen(st["scope"], i), "✅ Saved"


async def in_run_range(client, message, st):
    rng = parse_range(message.text or "")
    if not rng:
        return "retry", "❌ Send like <code>900</code>, <code>100 900</code> or a post link."
    status = await runner.start_job(client, int(st["scope"]), st["mode"], rng[0], rng[1], message.from_user.id, message)
    if status is None:
        return "done", ui.run_screen(st["scope"]), "⚠️ A job is already running. Stop it first."
    return "done", None, ""


INPUTS = {"addch": in_addch, "link_add": in_link_add, "link_url": in_link_url, "tpl_custom": in_tpl_custom,
          "old_add": in_old_add, "btn_text": in_btn_text, "btn_url": in_btn_url, "btn_many": in_btn_many,
          "btn_edit": in_btn_edit, "run_range": in_run_range}


@Client.on_message(filters.private & owner & has_pending, group=1)
async def on_input(client, message):
    uid = message.from_user.id
    st = pending.get(uid)
    if not st or (message.text or "").startswith("/"):
        return                                      # commands (/menu, /cancel ...) are handled by their own handlers
    handler = INPUTS.get(st["kind"])
    if handler is None:
        pending.clear(uid)
        return
    try:
        res = await handler(client, message, st)
    except Exception:
        log.exception("typed step %s failed", st["kind"])
        pending.clear(uid)
        await message.reply_text("⚠️ Something went wrong. Open /menu and try again.")
        return
    mode = res[0]
    if mode == "retry":
        await reply(message, ui.prompt_screen(res[1] + "\n\nTry again, or cancel.", st.get("scope", "m")))
    elif mode == "next":
        await reply(message, res[1])
    elif mode == "done":
        pending.clear(uid)
        if res[1]:
            await reply(message, res[1], res[2])
