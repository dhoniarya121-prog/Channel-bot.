"""Admin: caption settings, channel settings, force subscribe, security, maintenance & messages."""
import logging
import re

from pyrogram.errors import RPCError

from database import channels, settings
from keyboards.common import btn, kb
from utils import adminui, guards, router, state, tg
from utils.adminui import back, onoff
from utils.captions import build_caption, build_quote_template, make_key, validate_template, validate_url
from utils.text import esc, parse_int, trunc

log = logging.getLogger(__name__)
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


# ============================================================ captions
@router.cb("adm:c", "captions")
async def adm_captions(client, cq, args):
    on, active = await settings.get("auto_caption"), await settings.get("active_template")
    links = await settings.get("links")
    set_n = sum(1 for v in links.values() if v)
    await tg.show(cq, f"✏️ <b>Caption Settings</b>\n\nAutomatic caption editing: {onoff(on)}\nActive template: <b>{esc(active)}</b>\n"
                      f"Links configured: <b>{set_n}/{len(links)}</b>\nOld links to replace: <b>{len(await settings.get('old_links'))}</b>",
                  kb([btn(f"🔘 Auto caption: {onoff(on)}", "adm:c:tog")],
                     [btn("📝 Templates", "adm:c:tpl"), btn("🔗 Links", "adm:c:links")],
                     [btn("♻️ Old links", "adm:c:old"), btn("👁 Preview", "adm:c:pv")],
                     [btn("🔘 Channel Buttons", "adm:cb")], back()))


@router.cb("adm:c:tog", "captions")
async def adm_caption_toggle(client, cq, args):
    await settings.toggle("auto_caption")
    await adm_captions(client, cq, args)


@router.cb("adm:c:tpl", "captions")
async def adm_templates(client, cq, args):
    tpls, active = await settings.get("caption_templates"), await settings.get("active_template")
    rows = [[btn(("✅ " if n == active else "") + n, f"adm:c:tv:{n}")] for n in tpls]
    await tg.show(cq, "📝 <b>Caption templates</b>\n\nTap a template to view, use, edit or delete it.\n"
                      "Placeholders: <code>{original_caption}</code> " + " ".join(f"<code>{{{k}}}</code>/<code>{{{k}_at}}</code>" for k in (await settings.get("links"))) +
                      "\n<code>{name}</code> = URL, <code>{name_at}</code> = @username text.",
                  kb(*rows, [btn("🎨 Auto-build quote style", "adm:c:tq")], [btn("➕ New template", "adm:c:tn")], back("adm:c")))


@router.cb("adm:c:tv", "captions")
async def adm_template_view(client, cq, args):
    name = args[0]
    tpls = await settings.get("caption_templates")
    if name not in tpls:
        return ("Template not found.", True)
    active = await settings.get("active_template") == name
    await tg.show(cq, f"📝 <b>{esc(name)}</b>{' (active)' if active else ''}\n\n<pre>{esc(tpls[name])}</pre>",
                  kb([btn("✅ Use this", f"adm:c:use:{name}"), btn("✏️ Edit", f"adm:c:te:{name}")],
                     [btn("🗑 Delete", f"adm:c:td:{name}")], back("adm:c:tpl")))


@router.cb("adm:c:use", "captions")
async def adm_template_use(client, cq, args):
    if args[0] in await settings.get("caption_templates"):
        await settings.set("active_template", args[0])
    await adm_templates(client, cq, [])
    return "Template activated."


@router.cb("adm:c:td", "captions")
async def adm_template_delete(client, cq, args):
    tpls, active = await settings.get("caption_templates"), await settings.get("active_template")
    if args[0] == active or len(tpls) <= 1:
        return ("You can't delete the active or the only template.", True)
    tpls.pop(args[0], None)
    await settings.set("caption_templates", tpls)
    await adm_templates(client, cq, [])
    return "Deleted."


@router.cb("adm:c:te", "captions")
async def adm_template_edit(client, cq, args):
    await adminui.ask(cq, "adm_c_te", f"✏️ Send the new text for template <b>{esc(args[0])}</b>.\n\n"
                                      "Use HTML (<code>&lt;b&gt;</code>, <code>&lt;a href=\"{main_channel}\"&gt;Join&lt;/a&gt;</code>…). "
                                      "It must contain <code>{original_caption}</code>.", name=args[0])


@router.cb("adm:c:tn", "captions")
async def adm_template_new(client, cq, args):
    await adminui.ask(cq, "adm_c_tn", "➕ Send a <b>name</b> for the new template (letters, digits, _ or -, max 20):")


@router.on_input("adm_c_tn", "captions")
async def in_template_name(client, message, ctx):
    name = (message.text or "").strip()
    if not NAME_RE.match(name) or name in await settings.get("caption_templates"):
        state.set_state(message.from_user.id, "adm_c_tn")
        await message.reply_text("⚠️ Invalid or already used name. Try another (or /cancel).")
        return
    state.set_state(message.from_user.id, "adm_c_te", name=name)
    await message.reply_text(f"Now send the template text for <b>{esc(name)}</b> (HTML, must contain <code>{{original_caption}}</code>).")


@router.on_input("adm_c_te", "captions")
async def in_template_text(client, message, ctx):
    text = (message.text or "").strip()
    ok, err = validate_template(text, list((await settings.get("links")).keys()))
    if not ok:
        state.set_state(message.from_user.id, "adm_c_te", **ctx)
        await message.reply_text(f"❌ {esc(err)}\nSend a corrected version (or /cancel).")
        return
    tpls = await settings.get("caption_templates")
    tpls[ctx["name"]] = text
    await settings.set("caption_templates", tpls)
    await message.reply_text(f"✅ Template <b>{esc(ctx['name'])}</b> saved.", reply_markup=kb([btn("📝 Templates", "adm:c:tpl")], [btn("👁 Preview", "adm:c:pv")]))


def _label(k: str) -> str:
    return k.replace("_", " ").title()


@router.cb("adm:c:links", "captions")
async def adm_links(client, cq, args):
    links = await settings.get("links")
    rows = [[btn(f"{_label(k)}: {'✅' if v else '— not set'}", f"adm:c:ln:{k}"), btn("🗑", f"adm:c:lr:{k}")] for k, v in links.items()]
    body = "\n".join(f"• {_label(k)} → {esc(v or '—')}\n   <code>{{{k}}}</code> <code>{{{k}_at}}</code>" for k, v in links.items()) or "No links yet."
    await tg.show(cq, f"🔗 <b>Promotional links</b>\n\n{body}\n\nA template line whose link is not set is left out of captions.",
                  kb(*rows, [btn("➕ Add custom link", "adm:c:la")], back("adm:c")))


@router.cb("adm:c:ln", "captions")
async def adm_link_edit(client, cq, args):
    if args[0] not in await settings.get("links"):
        return ("Unknown link.", True)
    await adminui.ask(cq, "adm_c_ln", f"🔗 Send the new URL for <b>{_label(args[0])}</b> (https://…).\nSend <code>-</code> to clear it. "
                                      "The previous link is added to the old-links list automatically.", key=args[0])


@router.on_input("adm_c_ln", "captions")
async def in_link(client, message, ctx):
    raw = (message.text or "").strip()
    if raw != "-" and not validate_url(raw):
        state.set_state(message.from_user.id, "adm_c_ln", **ctx)
        await message.reply_text("⚠️ Invalid URL. It must start with http(s):// (or send - to clear).")
        return
    links = await settings.get("links")
    prev = links.get(ctx["key"])
    links[ctx["key"]] = "" if raw == "-" else raw
    await settings.set("links", links)
    if prev and prev != links[ctx["key"]]:
        old = await settings.get("old_links")
        if prev not in old:
            await settings.set("old_links", (old + [prev])[-50:])
    await message.reply_text("✅ Link updated.", reply_markup=kb([btn("🔗 Links", "adm:c:links")], [btn("👁 Preview", "adm:c:pv")]))


@router.cb("adm:c:la", "captions")
async def adm_link_add(client, cq, args):
    await adminui.ask(cq, "adm_c_la", "➕ Send <code>Name | https://t.me/username</code>\nExample: <code>Premium | https://t.me/wolfe_noxnetwork</code>")


@router.on_input("adm_c_la", "captions")
async def in_link_add(client, message, ctx):
    name, _, url = (message.text or "").partition("|")
    key, url = make_key(name), url.strip()
    links = await settings.get("links")
    if not key or not validate_url(url) or (key not in links and len(links) >= 12):
        state.set_state(message.from_user.id, "adm_c_la")
        await message.reply_text("⚠️ Format: <code>Name | https://…</code> (valid name, valid URL, max 12 links). Try again or /cancel.")
        return
    links[key] = url
    await settings.set("links", links)
    await message.reply_text(f"✅ Saved <b>{_label(key)}</b> — use <code>{{{key}}}</code> (URL) or <code>{{{key}_at}}</code> (@username) in templates.",
                             reply_markup=kb([btn("🔗 Links", "adm:c:links")], [btn("🎨 Build quote style", "adm:c:tq")]))


@router.cb("adm:c:lr", "captions")
async def adm_link_remove(client, cq, args):
    links = await settings.get("links")
    prev = links.pop(args[0], None)
    await settings.set("links", links)
    if prev:
        old = await settings.get("old_links")
        if prev not in old:
            await settings.set("old_links", (old + [prev])[-50:])
    await adm_links(client, cq, [])


@router.cb("adm:c:tq", "captions")
async def adm_quote_template(client, cq, args):
    links = await settings.get("links")
    keys = [k for k, v in links.items() if v] or list(links)
    if not keys:
        return ("Add at least one link first.", True)
    tpls = await settings.get("caption_templates")
    tpls["quote"] = build_quote_template(keys)
    await settings.set("caption_templates", tpls)
    await settings.set("active_template", "quote")
    await adm_preview(client, cq, [])
    return "Quote template built and activated."


@router.cb("adm:c:old", "captions")
async def adm_old_links(client, cq, args):
    old = await settings.get("old_links")
    rows = [[btn(f"🗑 {trunc(u, 40)}", f"adm:c:or:{i}")] for i, u in enumerate(old)]
    await tg.show(cq, "♻️ <b>Old links</b>\n\nLines containing these links (or their @usernames) are removed from captions "
                      "and replaced by the current template footer.", kb(*rows, [btn("➕ Add", "adm:c:oa"), btn("🧹 Clear all", "adm:c:oc")], back("adm:c")))


@router.cb("adm:c:or", "captions")
async def adm_old_remove(client, cq, args):
    old = await settings.get("old_links")
    if args[0].isdigit() and int(args[0]) < len(old):
        old.pop(int(args[0]))
        await settings.set("old_links", old)
    await adm_old_links(client, cq, [])


@router.cb("adm:c:oc", "captions")
async def adm_old_clear(client, cq, args):
    await settings.set("old_links", [])
    await adm_old_links(client, cq, [])


@router.cb("adm:c:oa", "captions")
async def adm_old_add(client, cq, args):
    await adminui.ask(cq, "adm_c_oa", "➕ Send an old link (https://t.me/…) or @username to strip from captions:")


@router.on_input("adm_c_oa", "captions")
async def in_old_add(client, message, ctx):
    v = (message.text or "").strip()
    if not (4 <= len(v) <= 200) or re.search(r"\s", v):
        state.set_state(message.from_user.id, "adm_c_oa")
        await message.reply_text("⚠️ Send a single link or @username (no spaces).")
        return
    if v.startswith("@"):
        v = "https://t.me/" + v[1:]
    old = await settings.get("old_links")
    if v not in old:
        await settings.set("old_links", (old + [v])[-50:])
    await message.reply_text("✅ Added.", reply_markup=kb([btn("♻️ Old links", "adm:c:old")]))


@router.cb("adm:c:pv", "captions")
async def adm_preview(client, cq, args):
    tpls = await settings.get("caption_templates")
    tpl = tpls.get(await settings.get("active_template")) or next(iter(tpls.values()))
    out = build_caption("<b>Sample Movie (2024)</b> 1080p WEB-DL", tpl, await settings.get("links"),
                        await settings.get("old_links"), "Sample.Movie.2024.mkv")
    await tg.show(cq, "👁 <b>Preview</b> (what the channel post caption will look like):\n\n" + out, kb(back("adm:c")))


# ============================================================ channels (caption sources)
def _ref(raw: str):
    raw = raw.strip()
    m = re.match(r"^(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/?$", raw)
    if m:
        return "@" + m.group(1)
    if re.fullmatch(r"-?\d{5,}", raw):
        return int(raw)
    if re.fullmatch(r"@?[A-Za-z0-9_]{4,}", raw):
        return "@" + raw.lstrip("@")
    return None


@router.cb("adm:ch", "channels")
async def adm_channels(client, cq, args):
    chs = await channels.list_role("source")
    rows = [[btn(f"🗑 {trunc(c['title'], 28)}", f"adm:ch:rm:{c['chat_id']}")] for c in chs]
    body = "\n".join(f"• {esc(c['title'])} (<code>{c['chat_id']}</code>)" for c in chs) or "No channels configured."
    await tg.show(cq, f"📡 <b>Channel Settings</b>\n\nCaption editing runs for files posted in:\n{body}\n\n"
                      "The bot must be an admin with the <b>Edit messages</b> right.",
                  kb(*rows, [btn("➕ Add channel", "adm:ch:add"), btn("🔍 Re-check permissions", "adm:ch:chk")],
                     [btn("🕘 Update old posts", "adm:ch:old"), btn("🛡 Content protection", "adm:ch:pt")], back()))


@router.cb("adm:ch:add", "channels")
async def adm_channel_add(client, cq, args):
    await adminui.ask(cq, "adm_ch_add", "➕ Send the channel <b>ID</b> (-100…), <b>@username</b> or t.me link.\nAdd the bot as admin first.")


@router.on_input("adm_ch_add", "channels")
async def in_channel_add(client, message, ctx):
    ref = _ref(message.text or "")
    if ref is None:
        await message.reply_text("⚠️ Not a valid channel reference.")
        return
    try:
        info = await tg.inspect_channel(client, ref)
    except (RPCError, ValueError, KeyError) as e:
        await message.reply_text(f"❌ Could not access that channel ({type(e).__name__}). Add the bot as admin and try again.")
        return
    if info["type"] != "CHANNEL":
        await message.reply_text("❌ That is not a channel.")
        return
    if not info["is_admin"] or not info["can_edit"]:
        await message.reply_text("❌ The bot must be a channel admin with the <b>Edit messages</b> right. Fix that and resend.")
        return
    new = await channels.add("source", info["chat_id"], info["title"], info["username"], None, info["private"])
    await message.reply_text(f"✅ {'Added' if new else 'Updated'}: <b>{esc(info['title'])}</b> (<code>{info['chat_id']}</code>)",
                             reply_markup=kb(back("adm:ch")))


@router.cb("adm:ch:rm", "channels")
async def adm_channel_remove(client, cq, args):
    await channels.remove("source", int(args[0]))
    await adm_channels(client, cq, [])


@router.cb("adm:ch:chk", "channels")
async def adm_channel_check(client, cq, args):
    lines = ["🔍 <b>Permission check</b>", ""]
    for c in await channels.list_role("source"):
        try:
            i = await tg.inspect_channel(client, c["chat_id"])
            lines.append(f"{'✅' if i['is_admin'] and i['can_edit'] else '❌'} {esc(c['title'])}: admin={i['is_admin']} edit={i['can_edit']}")
        except Exception as e:
            lines.append(f"❌ {esc(c['title'])}: {type(e).__name__}")
    if len(lines) == 2:
        lines.append("No channels configured.")
    await tg.show(cq, "\n".join(lines), kb(back("adm:ch")))


@router.cb("adm:ch:pt", "channels")
async def adm_protect(client, cq, args):
    """No args: list channels with their state. args = chat_id, 1|0: toggle 'restrict saving content'."""
    if len(args) == 2:
        try:
            await tg.safe(client.set_chat_protected_content, int(args[0]), args[1] == "1")
        except (AttributeError, RPCError) as e:
            return (f"Could not change it automatically ({type(e).__name__}). Do it by hand: channel → Manage → "
                    "Administrators/Permissions → turn on 'Restrict saving content'.", True)
    rows = []
    for c in await channels.list_role("source"):
        try:
            on = bool(getattr((await client.get_chat(c["chat_id"])), "has_protected_content", False))
        except Exception:
            rows.append([btn(f"❔ {trunc(c['title'], 28)} (cannot read)", f"adm:ch:pt:{c['chat_id']}:1")])
            continue
        rows.append([btn(f"{'🛡 ON' if on else '⚪ OFF'} · {trunc(c['title'], 26)}", f"adm:ch:pt:{c['chat_id']}:{0 if on else 1}")])
    await tg.show(cq, "🛡 <b>Channel content protection</b>\n\nWhen ON, people cannot forward, copy or save posts from the channel. "
                      "Tap a channel to switch. (Owner rights may be needed; otherwise use the Telegram setting by hand.)\n"
                      "This does not stop users from reporting a channel.", kb(*rows, back("adm:ch")))


# ============================================================ force subscribe
@router.cb("adm:fs", "forcesub")
async def adm_forcesub(client, cq, args):
    on = await settings.get("forcesub_enabled")
    chs = await channels.list_role("fsub")
    rows = [[btn(f"{'🔒' if c.get('private') else '📢'} {trunc(c['title'], 30)}", f"adm:fs:v:{c['chat_id']}")] for c in chs]
    await tg.show(cq, f"🔒 <b>Force Subscribe</b>\n\nStatus: {onoff(on)}\nChannels: <b>{len(chs)}</b>\n\n"
                      "Users must join every channel below before using the bot. The bot must be admin in each channel to verify membership.",
                  kb([btn(f"🔘 Force subscribe: {onoff(on)}", "adm:fs:tog")], *rows,
                     [btn("➕ Add channel", "adm:fs:add"), btn("🧪 Test my membership", "adm:fs:test")], back()))


@router.cb("adm:fs:tog", "forcesub")
async def adm_fs_toggle(client, cq, args):
    if not await settings.get("forcesub_enabled") and not await channels.list_role("fsub"):
        return ("Add at least one channel first.", True)
    await settings.toggle("forcesub_enabled")
    await adm_forcesub(client, cq, args)


@router.cb("adm:fs:add", "forcesub")
async def adm_fs_add(client, cq, args):
    await adminui.ask(cq, "adm_fs_add", "➕ Send: <code>channel [invite_link]</code>\n\nchannel = ID (-100…), @username or t.me link.\n"
                                        "Private channels need an invite link (sent here, or auto-created if the bot can invite users).")


@router.on_input("adm_fs_add", "forcesub")
async def in_fs_add(client, message, ctx):
    parts = (message.text or "").split()
    ref = _ref(parts[0]) if parts else None
    link = parts[1] if len(parts) > 1 else None
    if ref is None or (link and not validate_url(link)):
        await message.reply_text("⚠️ Format: <code>channel [https://t.me/+invite]</code>")
        return
    try:
        info = await tg.inspect_channel(client, ref)
    except (RPCError, ValueError, KeyError) as e:
        await message.reply_text(f"❌ Could not access that channel ({type(e).__name__}). Add the bot as admin first.")
        return
    if not info["is_admin"]:
        await message.reply_text("❌ The bot must be an admin of that channel to verify who has joined.")
        return
    if info["private"] and not link:
        link = await tg.export_invite(client, info["chat_id"])
        if not link:
            await message.reply_text("❌ Private channel: send an invite link, or give the bot the <b>Invite users</b> right.")
            return
    new = await channels.add("fsub", info["chat_id"], info["title"], info["username"], link, info["private"])
    await message.reply_text(f"✅ {'Added' if new else 'Updated'}: <b>{esc(info['title'])}</b> ({'private' if info['private'] else 'public'})",
                             reply_markup=kb(back("adm:fs")))


@router.cb("adm:fs:v", "forcesub")
async def adm_fs_view(client, cq, args):
    c = await channels.get("fsub", int(args[0]))
    if not c:
        return ("Channel not found.", True)
    await tg.show(cq, f"{'🔒 Private' if c.get('private') else '📢 Public'} channel <b>{esc(c['title'])}</b>\nID: <code>{c['chat_id']}</code>\n"
                      f"Join link: {esc(channels.join_url(c) or '— none —')}",
                  kb([btn("🔗 Set invite link", f"adm:fs:il:{c['chat_id']}"), btn("🗑 Remove", f"adm:fs:rm:{c['chat_id']}")], back("adm:fs")))


@router.cb("adm:fs:il", "forcesub")
async def adm_fs_invite_ask(client, cq, args):
    await adminui.ask(cq, "adm_fs_il", "🔗 Send the new invite link (https://t.me/…):", chat_id=int(args[0]))


@router.on_input("adm_fs_il", "forcesub")
async def in_fs_invite(client, message, ctx):
    link = (message.text or "").strip()
    if not validate_url(link):
        state.set_state(message.from_user.id, "adm_fs_il", **ctx)
        await message.reply_text("⚠️ Invalid URL.")
        return
    await channels.set_invite("fsub", ctx["chat_id"], link)
    await message.reply_text("✅ Invite link updated.", reply_markup=kb(back("adm:fs")))


@router.cb("adm:fs:rm", "forcesub")
async def adm_fs_remove(client, cq, args):
    await channels.remove("fsub", int(args[0]))
    await adm_forcesub(client, cq, [])


@router.cb("adm:fs:test", "forcesub")
async def adm_fs_test(client, cq, args):
    lines = ["🧪 <b>Your membership</b>", ""]
    for c in await channels.list_role("fsub"):
        r = await tg.is_member(client, c, cq.from_user.id)
        lines.append(f"{'✅' if r else '❌' if r is False else '❔ cannot verify'} {esc(c['title'])}")
    if len(lines) == 2:
        lines.append("No channels configured.")
    guards.forget(cq.from_user.id)
    await tg.show(cq, "\n".join(lines), kb(back("adm:fs")))


# ============================================================ security
adminui.number_setting("adm_sec_ms", "spam_mute_seconds", "Spam mute duration (seconds)", 10, 86400, "adm:sec", "security")
adminui.number_setting("adm_sec_mw", "max_warns", "Warnings before auto-ban", 1, 20, "adm:sec", "security")


@router.cb("adm:sec", "security")
async def adm_security(client, cq, args):
    s = {k: await settings.get(k) for k in ("antispam", "rate_limit_count", "rate_limit_window", "spam_mute_seconds",
                                            "max_warns", "require_verification", "protect_content")}
    await tg.show(cq, "🛡 <b>Security Settings</b>\n\n"
                      f"Anti-spam / rate limit: {onoff(s['antispam'])}\nLimit: <b>{s['rate_limit_count']}</b> actions per <b>{s['rate_limit_window']}s</b>\n"
                      f"Mute after 3 violations: <b>{s['spam_mute_seconds']}s</b>\nWarnings before auto-ban: <b>{s['max_warns']}</b>\n"
                      f"Require verification to share/submit: {onoff(s['require_verification'])}\n"
                      f"Block forward/save of delivered files (ignores the daily limit): {onoff(s['protect_content'])}",
                  kb([btn(f"🛡 Anti-spam: {onoff(s['antispam'])}", "adm:sec:as")], [btn("⏱ Rate limit", "adm:sec:rl"), btn("🔇 Mute time", "adm:sec:ms")],
                     [btn("⚠️ Max warns", "adm:sec:mw"), btn(f"✅ Verification: {onoff(s['require_verification'])}", "adm:sec:rv")],
                     [btn(f"🛡 Block forward/save of delivered files: {onoff(s['protect_content'])}", "adm:sec:pc")],
                     [btn("🚫 Banned users", "adm:u:banned:0")], back()))


@router.cb("adm:sec:pc", "security")
async def adm_sec_protect(client, cq, args):
    await settings.toggle("protect_content")
    await adm_security(client, cq, args)


@router.cb("adm:sec:as", "security")
async def adm_sec_antispam(client, cq, args):
    await settings.toggle("antispam")
    await adm_security(client, cq, args)


@router.cb("adm:sec:rv", "security")
async def adm_sec_verify(client, cq, args):
    await settings.toggle("require_verification")
    await adm_security(client, cq, args)


@router.cb("adm:sec:ms", "security")
async def adm_sec_mute(client, cq, args):
    await adminui.number_prompt(cq, "adm_sec_ms", "Spam mute duration (seconds)", await settings.get("spam_mute_seconds"), 10, 86400)


@router.cb("adm:sec:mw", "security")
async def adm_sec_warns(client, cq, args):
    await adminui.number_prompt(cq, "adm_sec_mw", "Warnings before auto-ban", await settings.get("max_warns"), 1, 20)


@router.cb("adm:sec:rl", "security")
async def adm_sec_rate(client, cq, args):
    await adminui.ask(cq, "adm_sec_rl", "⏱ Send <code>count seconds</code>, e.g. <code>8 10</code> = max 8 actions per 10 seconds (count 2–100, seconds 2–300).")


@router.on_input("adm_sec_rl", "security")
async def in_sec_rate(client, message, ctx):
    p = (message.text or "").split()
    c, w = (parse_int(p[0], 2, 100), parse_int(p[1], 2, 300)) if len(p) == 2 else (None, None)
    if c is None or w is None:
        state.set_state(message.from_user.id, "adm_sec_rl")
        await message.reply_text("⚠️ Format: <code>count seconds</code> e.g. <code>8 10</code>")
        return
    await settings.set("rate_limit_count", c)
    await settings.set("rate_limit_window", w)
    await message.reply_text(f"✅ Limit: {c} actions per {w}s.", reply_markup=kb(back("adm:sec")))


# ============================================================ maintenance + messages
@router.cb("adm:mt", "maintenance")
async def adm_maintenance(client, cq, args):
    on = await settings.get("maintenance")
    sm = await settings.get("start_message")
    await tg.show(cq, f"🛠 <b>Maintenance & Messages</b>\n\nMaintenance mode: {onoff(on)} (admins are never blocked)\n"
                      f"Message: {esc(await settings.get('maintenance_msg'))}\n\nCustom /start message — EN: {'set' if sm.get('en') else 'default'}, HI: {'set' if sm.get('hi') else 'default'}\n"
                      "Placeholders: <code>{name} {bot} {quota} {plan}</code>",
                  kb([btn(f"🔘 Maintenance: {onoff(on)}", "adm:mt:tog")], [btn("✏️ Maintenance message", "adm:mt:msg")],
                     [btn("✏️ Start message (EN)", "adm:mt:sm:en"), btn("✏️ Start message (HI)", "adm:mt:sm:hi")], back()))


@router.cb("adm:mt:tog", "maintenance")
async def adm_maint_toggle(client, cq, args):
    await settings.toggle("maintenance")
    await adm_maintenance(client, cq, args)


@router.cb("adm:mt:msg", "maintenance")
async def adm_maint_msg(client, cq, args):
    await adminui.ask(cq, "adm_mt_msg", "✏️ Send the message users see during maintenance (HTML allowed):")


@router.on_input("adm_mt_msg", "maintenance")
async def in_maint_msg(client, message, ctx):
    text = (message.text or "").strip()
    if not 3 <= len(text) <= 1000:
        state.set_state(message.from_user.id, "adm_mt_msg")
        await message.reply_text("⚠️ 3–1000 characters please.")
        return
    await settings.set("maintenance_msg", text)
    await message.reply_text("✅ Saved.", reply_markup=kb(back("adm:mt")))


@router.cb("adm:mt:sm", "maintenance")
async def adm_start_msg(client, cq, args):
    lang = args[0] if args and args[0] in ("en", "hi") else "en"
    await adminui.ask(cq, "adm_mt_sm", f"✏️ Send the custom /start message ({lang.upper()}). HTML allowed. Send <code>-</code> to restore the default.", lang=lang)


@router.on_input("adm_mt_sm", "maintenance")
async def in_start_msg(client, message, ctx):
    text = (message.text or "").strip()
    if not 1 <= len(text) <= 1500:
        state.set_state(message.from_user.id, "adm_mt_sm", **ctx)
        await message.reply_text("⚠️ 1–1500 characters please.")
        return
    await settings.update_in("start_message", ctx["lang"], "" if text == "-" else text)
    await message.reply_text("✅ Saved.", reply_markup=kb(back("adm:mt")))
