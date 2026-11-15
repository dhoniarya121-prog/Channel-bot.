"""Admin: permanent URL-button panels for channel posts (like the 'Films Chor' link panel)."""
import asyncio
import logging

from pyrogram.errors import MessageNotModified, RPCError

from database import channels, files, mongo, settings
from keyboards.channel import channel_markup
from keyboards.common import btn, kb
from utils import adminui, router, state, tg
from utils.adminui import back, onoff
from utils.buttons import MAX_BUTTONS, merge, parse_lines, parse_post_link
from utils.text import esc, trunc

log = logging.getLogger(__name__)
_RUNNING = {"reapply": False}


@router.cb("adm:cb", "captions")
async def adm_buttons(client, cq, args):
    on, per = await settings.get("buttons_enabled"), await settings.get("buttons_per_row")
    items = await settings.get("channel_buttons")
    rows = [[btn("⬆️", f"adm:cb:up:{i}"), btn(f"🗑 {trunc(b['text'], 28)}", f"adm:cb:rm:{i}")] for i, b in enumerate(items)]
    await tg.show(cq, "🔘 <b>Channel Buttons</b>\n\nURL buttons shown under channel posts (they stay on the post permanently).\n\n"
                      f"Auto-attach to NEW posts: {onoff(on)}\nButtons: <b>{len(items)}/{MAX_BUTTONS}</b> · per row: <b>{per}</b>",
                  kb(*rows,
                     [btn("➕ Add buttons", "adm:cb:add"), btn(f"↔️ Per row: {per}", "adm:cb:pr")],
                     [btn(f"🔘 Auto-attach: {onoff(on)}", "adm:cb:tog"), btn("👁 Preview", "adm:cb:pv")],
                     [btn("📤 Post a panel in a channel", "adm:cb:post")],
                     [btn("🔗 Apply to a post link", "adm:cb:link"), btn("♻️ Re-apply to indexed posts", "adm:cb:all")],
                     back("adm:c")))


@router.cb("adm:cb:tog", "captions")
async def adm_cb_toggle(client, cq, args):
    if not await settings.get("buttons_enabled") and not await settings.get("channel_buttons"):
        return ("Add at least one button first.", True)
    await settings.toggle("buttons_enabled")
    await adm_buttons(client, cq, args)


@router.cb("adm:cb:pr", "captions")
async def adm_cb_per_row(client, cq, args):
    await settings.set("buttons_per_row", 2 if await settings.get("buttons_per_row") == 1 else 1)
    await adm_buttons(client, cq, args)


@router.cb("adm:cb:add", "captions")
async def adm_cb_add(client, cq, args):
    await adminui.ask(cq, "adm_cb_add", "➕ Send one or more buttons, <b>one per line</b>:\n\n"
                                        "<code>Main Channel | https://t.me/yourchannel\nMovie Bot | https://t.me/yourbot</code>")


@router.on_input("adm_cb_add", "captions")
async def in_cb_add(client, message, ctx):
    new, errors = parse_lines(message.text or "")
    if errors or not new:
        state.set_state(message.from_user.id, "adm_cb_add")
        await message.reply_text("❌ " + ("\n".join(esc(e) for e in errors) or "Nothing to add.") + "\n\nSend the corrected list (or /cancel).")
        return
    merged, added, skipped = merge(await settings.get("channel_buttons"), new)
    await settings.set("channel_buttons", merged)
    await message.reply_text(f"✅ Added <b>{added}</b> button(s)." + (f" Skipped {skipped} (duplicate URL or limit {MAX_BUTTONS})." if skipped else ""),
                             reply_markup=kb([btn("🔘 Channel Buttons", "adm:cb")]))


@router.cb("adm:cb:rm", "captions")
async def adm_cb_remove(client, cq, args):
    items = await settings.get("channel_buttons")
    if args and args[0].isdigit() and int(args[0]) < len(items):
        items.pop(int(args[0]))
        await settings.set("channel_buttons", items)
        if not items:
            await settings.set("buttons_enabled", False)
    await adm_buttons(client, cq, [])


@router.cb("adm:cb:up", "captions")
async def adm_cb_up(client, cq, args):
    items = await settings.get("channel_buttons")
    i = int(args[0]) if args and args[0].isdigit() else 0
    if 0 < i < len(items):
        items[i - 1], items[i] = items[i], items[i - 1]
        await settings.set("channel_buttons", items)
    await adm_buttons(client, cq, [])


@router.cb("adm:cb:pv", "captions")
async def adm_cb_preview(client, cq, args):
    markup = await channel_markup(force=True)
    if not markup:
        return ("No buttons yet.", True)
    await tg.reply(cq, "👁 <b>Preview</b> – this is how the buttons look under a post:", markup)


# ---- post a fresh panel (photo/text + buttons) into a channel
@router.cb("adm:cb:post", "captions")
async def adm_cb_post(client, cq, args):
    chs = await channels.list_role("source")
    if not chs or not await settings.get("channel_buttons"):
        return ("Add buttons and at least one channel (Channel Settings) first.", True)
    await tg.show(cq, "📤 Choose the channel to post the panel in:",
                  kb(*[[btn(trunc(c["title"], 30), f"adm:cb:pc:{c['chat_id']}")] for c in chs], back("adm:cb")))


@router.cb("adm:cb:pc", "captions")
async def adm_cb_pick(client, cq, args):
    await adminui.ask(cq, "adm_cb_post", "📤 Now send the post (photo/video/text with caption) — it will be copied to the channel "
                                         "with your buttons attached.", chat_id=int(args[0]))


@router.on_input("adm_cb_post", "captions")
async def in_cb_post(client, message, ctx):
    markup = await channel_markup(force=True)
    if not markup:
        await message.reply_text("❌ No buttons configured.")
        return
    try:
        sent = await tg.safe(client.copy_message, ctx["chat_id"], message.chat.id, message.id, reply_markup=markup)
    except RPCError as e:
        await message.reply_text(f"❌ Could not post ({type(e).__name__}). The bot needs the <b>Post messages</b> right in that channel.")
        return
    await message.reply_text(f"✅ Posted (message id <code>{sent.id}</code>). Pin it in the channel if you want it on top.",
                             reply_markup=kb(back("adm:cb")))


# ---- apply to one existing post
@router.cb("adm:cb:link", "captions")
async def adm_cb_link(client, cq, args):
    await adminui.ask(cq, "adm_cb_link", "🔗 Send the link of the channel post (e.g. <code>https://t.me/c/123456789/45</code> or "
                                         "<code>https://t.me/yourchannel/45</code>) to attach the buttons to.")


@router.on_input("adm_cb_link", "captions")
async def in_cb_link(client, message, ctx):
    ref = parse_post_link(message.text or "")
    markup = await channel_markup(force=True)
    if not ref or not markup:
        state.set_state(message.from_user.id, "adm_cb_link")
        await message.reply_text("⚠️ Send a valid post link, and make sure buttons exist. (or /cancel)")
        return
    try:
        await tg.safe(client.edit_message_reply_markup, ref[0], ref[1], markup)
    except MessageNotModified:
        pass
    except RPCError as e:
        await message.reply_text(f"❌ Failed ({type(e).__name__}). The bot must be admin with <b>Edit messages</b> in that channel.")
        return
    await message.reply_text("✅ Buttons attached to that post.", reply_markup=kb(back("adm:cb")))


# ---- re-apply to every post the bot has indexed
@router.cb("adm:cb:all", "captions")
async def adm_cb_all_ask(client, cq, args):
    n = await mongo.col(mongo.FILES).count_documents({"source": "channel"})
    await tg.show(cq, f"♻️ Re-apply the current buttons to <b>{n}</b> channel posts the bot has indexed?\n"
                      "(Posts made before the bot joined are not known to it – use <i>Apply to a post link</i> for those.)\n"
                      "It runs in the background, about 1 post per second.",
                  kb([btn("✅ Start", "adm:cb:all2"), btn("✖️ Cancel", "adm:cb")]))


@router.cb("adm:cb:all2", "captions")
async def adm_cb_all(client, cq, args):
    if _RUNNING["reapply"]:
        return ("Already running.", True)
    markup = await channel_markup(force=True)
    if not markup:
        return ("No buttons configured.", True)
    admin_id = cq.from_user.id
    _RUNNING["reapply"] = True
    await tg.show(cq, "♻️ Started. You will get a message when it finishes.", kb(back("adm:cb")))

    async def job():
        done = failed = 0
        try:
            rows = await mongo.col(mongo.FILES).find({"source": "channel"}).to_list(None)
            for f in rows:
                try:
                    await tg.safe(client.edit_message_reply_markup, f["chat_id"], f["message_id"], markup)
                    done += 1
                except MessageNotModified:
                    done += 1
                except RPCError:
                    failed += 1
                await asyncio.sleep(1)
        finally:
            _RUNNING["reapply"] = False
        await tg.notify(client, admin_id, f"♻️ Buttons re-applied.\n✅ {done}  ❌ {failed} (deleted posts or missing rights)")
    asyncio.create_task(job())
