"""Menu screens for the bot panel. Every function returns (html_text, rows); rows are lists of
{text, data} buttons (callback_data is always short: `code:scope:arg`). No Telegram dependency.

Scope = "d" (default settings every channel inherits) or a channel id.
"""
from urllib.parse import urlparse

import config
from utils import jobs, store, templates
from utils.buttons import MAX_BUTTONS
from utils.captions import label
from utils.runner import MODES
from utils.text import esc, trunc

D = store.DEFAULT
PER_PAGE = 8


def b(text: str, data: str) -> dict:
    return {"text": text, "data": data}


def _on(v) -> str:
    return "ON ✅" if v else "OFF ❌"


def _host(url: str) -> str:
    p = urlparse(url)
    return trunc((p.netloc + p.path).rstrip("/"), 40)


def scope_name(scope) -> str:
    if store.key(scope) == D:
        return "🌐 Default settings"
    c = store.get(scope)
    return "📡 " + esc((c or {}).get("title") or scope)


def missing(back: str = "chs:0") -> tuple[str, list]:
    return "⚠️ That channel is no longer in the list.", [[b("⬅ Back", back)]]


# ---- main -------------------------------------------------------------------------------------------------
def main_screen() -> tuple[str, list]:
    n = len(store.list_channels())
    text = (f"🤖 <b>{esc(config.BOT_NAME)}</b>  <i>v{config.VERSION}</i>\n\n📡 Channels: <b>{n}</b>\n\n"
            "Everything is controlled from these buttons — no file editing needed.")
    return text, [[b("📡 My Channels", "chs:0"), b("➕ Add Channel", "add")],
                  [b("🌐 Default Settings", "ch:d"), b("👁 Preview", "pv:d")],
                  [b("💾 Backup", "bk"), b("❓ Help", "help")]]


def help_screen() -> tuple[str, list]:
    text = ("❓ <b>How it works</b>\n\n"
            "1️⃣ Make me <b>admin</b> in your channel (<i>Edit messages</i> right).\n"
            "2️⃣ <b>➕ Add Channel</b> (or just post once — I notice the channel myself).\n"
            "3️⃣ Open the channel and set:\n"
            "• 🎨 <b>Template</b> – caption design\n• 🔗 <b>Links</b> – names + URLs used in the design\n"
            "• 🔘 <b>Buttons</b> – link buttons shown under every post\n"
            "• ▶️ <b>Run on old posts</b> – apply captions/buttons to posts already in the channel\n\n"
            "🌐 <b>Default Settings</b> are used by every channel that has no settings of its own.\n\n"
            "Commands: /menu /preview /id /backup /restore /cancel")
    return text, [[b("⬅ Menu", "m")]]


def prompt_screen(text: str, scope: str = "m") -> tuple[str, list]:
    return text, [[b("❌ Cancel", f"x:{scope}")]]


# ---- channels ---------------------------------------------------------------------------------------------
def channels_screen(page: int = 0) -> tuple[str, list]:
    chs = store.list_channels()
    pages = max(1, -(-len(chs) // PER_PAGE))
    page = max(0, min(page, pages - 1))
    rows = []
    for cid, c in chs[page * PER_PAGE:(page + 1) * PER_PAGE]:
        flags = ("📝" if c["caption"] else "▫️") + ("🔘" if c["buttons"] and c["buttons_on"] else "▫️")
        rows.append([b(f"{flags} {trunc(c.get('title') or cid, 30)}", f"ch:{cid}")])
    if pages > 1:
        rows.append([b("⬅", f"chs:{page - 1}") if page else b("·", "noop"), b(f"{page + 1}/{pages}", "noop"),
                     b("➡", f"chs:{page + 1}") if page < pages - 1 else b("·", "noop")])
    rows.append([b("➕ Add Channel", "add"), b("⬅ Menu", "m")])
    text = "📡 <b>My Channels</b>\n\n" + ("Tap a channel to manage it.\n📝 = auto caption  🔘 = auto buttons" if chs else
                                         "No channels yet.\nTap ➕ <b>Add Channel</b> — or post something in a channel "
                                         "where I am admin and I will add it myself.")
    return text, rows


def channel_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    c = store.get(k)
    if c is None:
        return missing()
    e = store.effective(k)
    tname = templates.name(e["template_key"]) + ("" if e["own_template"] or k == D else "  <i>(default)</i>")
    links = f"{len(e['links'])}" + ("" if e["own_links"] or k == D else "  <i>(default)</i>")
    if k == D:
        text = (f"🌐 <b>Default settings</b>\n<i>Used by every channel that has no settings of its own.</i>\n\n"
                f"🎨 Template: <b>{tname}</b>\n🔗 Links: <b>{links}</b>\n🧹 Old links to remove: <b>{len(e['old_links'])}</b>")
        rows = [[b("🎨 Template", f"tpl:{k}"), b("🔗 Links", f"lk:{k}")],
                [b("🧹 Old links", f"ol:{k}"), b("👁 Preview", f"pv:{k}")],
                [b("⬅ Menu", "m")]]
        return text, rows
    n_btn = len(e["buttons"])
    text = (f"📡 <b>{esc(c.get('title') or k)}</b>\n<code>{k}</code>\n\n"
            f"📝 Auto caption: <b>{_on(e['caption'])}</b>\n"
            f"🔘 Auto buttons: <b>{_on(e['buttons_on'])}</b>  ({n_btn} button{'s' if n_btn != 1 else ''})\n"
            f"🎨 Template: <b>{tname}</b>\n🔗 Links: <b>{links}</b>\n"
            f"🧹 Old links to remove: <b>{len(e['old_links'])}</b>")
    rows = [[b(f"📝 Caption: {_on(e['caption'])}", f"tg:{k}:cap"), b(f"🔘 Buttons: {_on(e['buttons_on'])}", f"tg:{k}:btn")],
            [b("🎨 Template", f"tpl:{k}"), b("🔗 Links", f"lk:{k}")],
            [b(f"🔘 Manage buttons ({n_btn})", f"bt:{k}")],
            [b("🧹 Old links", f"ol:{k}"), b("👁 Preview", f"pv:{k}")],
            [b("▶️ Run on old posts", f"run:{k}")],
            [b("🗑 Remove channel", f"rc:{k}"), b("⬅ Back", "chs:0")]]
    return text, rows


def confirm_remove_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    return (f"🗑 Remove {scope_name(k)} from the list?\n\nIts settings are deleted. Posts already edited stay as they are.",
            [[b("✅ Yes, remove", f"rmy:{k}"), b("❌ No", f"ch:{k}")]])


# ---- template ---------------------------------------------------------------------------------------------
def template_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    if store.get(k) is None:
        return missing()
    e = store.effective(k)
    own = e["own_template"] or k == D
    rows = []
    for key, name in templates.PRESETS.items():
        mark = "✅ " if own and e["template_key"] == key else ""
        rows.append([b(mark + name, f"tps:{k}:{key}")])
    rows.append([b(("✅ " if own and e["template_key"] == templates.CUSTOM else "") + "✍️ Custom template", f"tpc:{k}")])
    if k != D:
        rows.append([b(("✅ " if not own else "") + "↩️ Use default template", f"tps:{k}:inherit")])
    rows.append([b("👁 Preview", f"pv:{k}"), b("⬅ Back", f"ch:{k}")])
    text = (f"🎨 <b>Template</b> — {scope_name(k)}\n\nNow: <b>{templates.name(e['template_key'])}</b>"
            f"{'' if own else '  <i>(from default)</i>'}\n\nPick a design. Links used in the design come from 🔗 Links.")
    return text, rows


def custom_template_prompt(scope) -> tuple[str, list]:
    k = store.key(scope)
    keys = list(store.effective(k)["links"])
    ph = "\n".join(f"<code>{{{x}}}</code> → url   <code>{{{x}_at}}</code> → @name" for x in keys[:10]) or "(no links yet)"
    text = ("✍️ <b>Custom template</b>\n\nSend your caption design as one message, using HTML tags "
            "(<code>&lt;b&gt; &lt;i&gt; &lt;a href=\"…\"&gt; &lt;blockquote&gt;</code>).\n\n"
            "It <b>must</b> contain <code>{original_caption}</code> (the movie/file text).\nLinks you can use:\n" + ph +
            "\n\nExample:\n<code>{original_caption}\n\n&lt;a href=\"{main_channel}\"&gt;Join&lt;/a&gt;</code>")
    return prompt_screen(text, k)


# ---- links ------------------------------------------------------------------------------------------------
def links_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    if store.get(k) is None:
        return missing()
    e = store.effective(k)
    lines = "\n".join(f"• <code>{x}</code> → {esc(u)}" for x, u in e["links"].items()) or "<i>No links yet.</i>"
    note = "" if e["own_links"] or k == D else "\n<i>These are the default links. Change anything and this channel gets its own copy.</i>"
    text = f"🔗 <b>Links</b> — {scope_name(k)}\n\n{lines}\n{note}\n\nTap a link to change or delete it."
    items = [b(f"🔗 {trunc(label(x), 18)}", f"lki:{k}:{x}") for x in e["links"]]
    rows = [items[i:i + 2] for i in range(0, len(items), 2)]
    rows.append([b("➕ Add link", f"lka:{k}")])
    if k != D and e["own_links"]:
        rows.append([b("♻️ Use default links", f"lkr:{k}")])
    rows.append([b("⬅ Back", f"ch:{k}")])
    return text, rows


def link_screen(scope, name: str) -> tuple[str, list]:
    k = store.key(scope)
    url = store.effective(k)["links"].get(name)
    if url is None:
        return links_screen(k)
    text = (f"🔗 <b>{esc(label(name))}</b>\n{esc(url)}\n\nUse it in a custom template as:\n"
            f"<code>{{{name}}}</code> (url)   <code>{{{name}_at}}</code> (@name)")
    return text, [[b("✏️ Change URL", f"lke:{k}:{name}"), b("🗑 Delete", f"lkd:{k}:{name}")],
                  [b("⬅ Back", f"lk:{k}")]]


def link_add_prompt(scope) -> tuple[str, list]:
    k = store.key(scope)
    return prompt_screen("➕ <b>Add link</b>\n\nSend: <code>name | https://t.me/yourchannel</code>\n"
                         "Example: <code>backup | @roaroic0</code>", k)


# ---- old links --------------------------------------------------------------------------------------------
def oldlinks_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    if store.get(k) is None:
        return missing()
    e = store.effective(k)
    lines = "\n".join("• " + esc(x) for x in e["old_links"]) or "<i>None.</i>"
    note = "" if e["own_old_links"] or k == D else "\n<i>(default list)</i>"
    text = (f"🧹 <b>Old links to remove</b> — {scope_name(k)}{note}\n\nLinks / @handles listed here are "
            f"stripped from captions before the new design is added.\n\n{lines}")
    rows = [[b("➕ Add", f"ola:{k}"), b("🧹 " + ("Clear" if k == D else "Clear / use default"), f"olc:{k}")],
            [b("⬅ Back", f"ch:{k}")]]
    return text, rows


def oldlinks_add_prompt(scope) -> tuple[str, list]:
    k = store.key(scope)
    return prompt_screen("🧹 <b>Add old links</b>\n\nSend links or @handles to remove from captions "
                         "(several allowed, space or new line).\nExample: <code>@oldchannel https://t.me/oldgroup</code>", k)


# ---- buttons ----------------------------------------------------------------------------------------------
def buttons_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    c = store.get(k)
    if c is None or k == D:
        return missing()
    btns = c["buttons"]
    lines = "\n".join(f"{i}. <b>{esc(x['text'])}</b> → {esc(_host(x['url']))}" for i, x in enumerate(btns, 1)) \
        or "<i>No buttons yet. Tap ➕ Add button.</i>"
    text = (f"🔘 <b>Buttons</b> — {scope_name(k)}\n{len(btns)}/{MAX_BUTTONS} · auto: <b>{_on(c['buttons_on'])}</b>\n\n{lines}\n\n"
            "These link buttons appear under every new post. Use ▶️ <b>Run on old posts</b> to add them to old posts.")
    rows = [[b(f"{i}. {trunc(x['text'], 28)}", f"bti:{k}:{i - 1}")] for i, x in enumerate(btns, 1)]
    rows.append([b("➕ Add button", f"bta:{k}"), b("📋 Add many", f"btm:{k}")])
    rows.append([b(("✅ " if c["per_row"] == 1 else "") + "▫️ 1 per row", f"btr:{k}:1"),
                 b(("✅ " if c["per_row"] == 2 else "") + "▫️▫️ 2 per row", f"btr:{k}:2")])
    rows.append([b(f"🔘 Auto buttons: {_on(c['buttons_on'])}", f"tg:{k}:btnb")])
    if btns:
        rows.append([b("🧹 Clear all", f"btc:{k}"), b("👁 Preview", f"pv:{k}")])
    rows.append([b("⬅ Back", f"ch:{k}")])
    return text, rows


def button_screen(scope, idx: int) -> tuple[str, list]:
    k = store.key(scope)
    btns = store.buttons(k)
    if not 0 <= idx < len(btns):
        return buttons_screen(k)
    x = btns[idx]
    text = f"🔘 <b>Button {idx + 1}</b>\n\nText: <b>{esc(x['text'])}</b>\nLink: {esc(x['url'])}"
    return text, [[b("✏️ Text", f"bte:{k}:{idx}:t"), b("🔗 Link", f"bte:{k}:{idx}:u")],
                  [b("⬆️ Up", f"btu:{k}:{idx}"), b("⬇️ Down", f"btd:{k}:{idx}")],
                  [b("🗑 Delete", f"btx:{k}:{idx}"), b("⬅ Back", f"bt:{k}")]]


def button_add_prompt(step: int, scope) -> tuple[str, list]:
    k = store.key(scope)
    if step == 1:
        return prompt_screen(f"➕ <b>New button</b> — step 1/2\n\nSend the <b>text</b> shown on the button "
                             f"(max 40 characters).\nExample: <code>🎬 Movie Updates</code>", k)
    return prompt_screen("➕ <b>New button</b> — step 2/2\n\nNow send the <b>link</b> it opens.\n"
                         "Example: <code>https://t.me/roaroic1</code> or <code>@roaroic1</code>", k)


def buttons_many_prompt(scope) -> tuple[str, list]:
    k = store.key(scope)
    return prompt_screen("📋 <b>Add many buttons</b>\n\nOne per line:\n<code>Text | https://link</code>\n\nExample:\n"
                         "<code>🎬 Movies | https://t.me/roaroic1\n🤖 Bot | @roaroic_bot</code>", k)


def button_edit_prompt(scope, idx: int, what: str) -> tuple[str, list]:
    k = store.key(scope)
    return prompt_screen("✏️ Send the new <b>text</b> for this button." if what == "t" else
                         "🔗 Send the new <b>link</b> for this button.", k)


def confirm_clear_buttons(scope) -> tuple[str, list]:
    k = store.key(scope)
    return "🧹 Delete <b>all</b> buttons of this channel?", [[b("✅ Yes", f"btcy:{k}"), b("❌ No", f"bt:{k}")]]


# ---- run on old posts -------------------------------------------------------------------------------------
def run_screen(scope) -> tuple[str, list]:
    k = store.key(scope)
    c = store.get(k)
    if c is None or k == D:
        return missing()
    busy = jobs.busy()
    text = (f"▶️ <b>Run on old posts</b> — {scope_name(k)}\n\nChoose what to do with posts that are already in the channel. "
            "Next I will ask for the range of post IDs.\n\n📝 <b>Captions</b> – apply this channel's caption design\n"
            "🔘 <b>Buttons</b> – add this channel's buttons\n📝🔘 <b>Both</b>\n🚫 <b>Remove buttons</b> from old posts")
    rows = []
    if busy:
        text += f"\n\n⏳ A job is running now ({esc(busy)})."
        rows.append([b("⏹ Stop running job", "stop")])
    rows += [[b(MODES["caption"], f"rm:{k}:caption"), b(MODES["buttons"], f"rm:{k}:buttons")],
             [b(MODES["both"], f"rm:{k}:both")], [b(MODES["unbutton"], f"rm:{k}:unbutton")],
             [b("⬅ Back", f"ch:{k}")]]
    return text, rows


def run_range_prompt(scope, mode: str) -> tuple[str, list]:
    k = store.key(scope)
    return prompt_screen(f"▶️ <b>{MODES.get(mode, mode)}</b>\n\nSend the range of post IDs:\n"
                         "• <code>900</code> → posts 1 to 900\n• <code>100 900</code> → posts 100 to 900\n"
                         "• a post link, e.g. <code>https://t.me/c/1234567890/900</code> → 1 to that post\n\n"
                         "Tip: open your <b>latest</b> post, copy its link and send it here.", k)
