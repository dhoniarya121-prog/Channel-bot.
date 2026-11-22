"""20 ready-made caption designs (pick them in 🎨 Template). Each link is used once per design;
a line whose link is not set is skipped automatically. Text styles differ: bold, italic, underline,
mono, small caps, bold-sans, serif and script letters."""
from utils.fonts import fancy as F

M = '<a href="{main_channel}">'
B = '<a href="{backup_channel}">'
BOT = '<a href="{movie_bot}">'
G = '<a href="{movies_group}">'
D = '<a href="{discussion_group}">'
N = '<a href="{notification_channel}">'

DESIGNS: dict[str, tuple[str, str]] = {
    "d01": ("1 · Classic Clean", (
        "🎬 <b>{original_caption}</b>\n\n"
        "📢 " + M + "Main Channel</a>  |  💾 " + B + "Backup</a>")),
    "d02": ("2 · Quote Box", (
        "<b>{original_caption}</b>\n\n"
        "<blockquote>📢 " + M + "Main Channel</a>\n"
        "💾 " + B + "Backup Channel</a>\n"
        "💬 " + D + "Request Group</a></blockquote>")),
    "d03": ("3 · Minimal Line", (
        "{original_caption}\n\n"
        "<i>—</i> <u>" + M + "Join us</a></u>")),
    "d04": ("4 · Cinematic", (
        "🎥 ━━━━━━━━━━━━━━━\n"
        "<b>{original_caption}</b>\n"
        "━━━━━━━━━━━━━━━ 🎥\n"
        "🍿 " + M + "Watch more movies</a>")),
    "d05": ("5 · Premium Frame", (
        "╔═══════════════╗\n"
        "  <b>{original_caption}</b>\n"
        "╚═══════════════╝\n"
        "⭐ " + M + F("Main", "bold") + "</a>\n"
        "⭐ " + B + F("Backup", "bold") + "</a>")),
    "d06": ("6 · Bracket Header", (
        "<b>[ {backup_channel_at} ]</b> {original_caption}\n\n"
        "➤ " + M + "Main Channel</a>")),
    "d07": ("7 · Emoji Stack", (
        "🎬 <b>{original_caption}</b>\n\n"
        "📢 <code>Join</code>   {main_channel_at}\n"
        "💾 <code>Backup</code> {backup_channel_at}\n"
        "🤖 <code>Bot</code>    {movie_bot_at}")),
    "d08": ("8 · Tag Style", (
        "#NewUpload #Movies\n"
        "<b>{original_caption}</b>\n"
        "🔔 " + N + "Get notified</a>")),
    "d09": ("9 · Dotted Divider", (
        "<b>{original_caption}</b>\n"
        "• • • • • • • • • • •\n"
        "📢 {main_channel_at} • 💾 {backup_channel_at}\n"
        "<i>" + F("join for more updates", "small") + "</i>")),
    "d10": ("10 · Arrow List", (
        "<b>{original_caption}</b>\n\n"
        "➥ " + M + "Main Channel</a>\n"
        "➥ " + B + "Backup Channel</a>\n"
        "➥ " + D + "Request Group</a>")),
    "d11": ("11 · Fire Banner", (
        "🔥🔥🔥 <b>NEW UPLOAD</b> 🔥🔥🔥\n"
        "{original_caption}\n"
        "👉 " + M + "<b>Join now</b></a>")),
    "d12": ("12 · Hinglish", (
        "🎬 <b>{original_caption}</b>\n\n"
        "<i>Channel join karo aur updates pao 👇</i>\n"
        "📢 {main_channel_at}")),
    "d13": ("13 · Info Card", (
        "📌 <b>Title:</b> {original_caption}\n"
        "📢 <b>Join:</b> {main_channel_at}\n"
        "💾 <b>Backup:</b> {backup_channel_at}")),
    "d14": ("14 · Double Quote", (
        "<blockquote><b>{original_caption}</b></blockquote>\n\n"
        "<blockquote>📢 {main_channel_at}  💾 {backup_channel_at}</blockquote>")),
    "d15": ("15 · Neon Box", (
        "┏━━━━━━━━━━━━━┓\n"
        "┃ 🎬 <code>{original_caption}</code>\n"
        "┗━━━━━━━━━━━━━┛\n"
        "📢 {main_channel_at}")),
    "d16": ("16 · Star Script", (
        "🌟 <b>{original_caption}</b>\n"
        "✨ " + F("Powered by", "script") + " {main_channel_at}")),
    "d17": ("17 · Backup Highlight", (
        "<b>{original_caption}</b>\n\n"
        "⚠️ <i>Channel band ho jaye to yahan aao:</i>\n"
        "💾 " + B + "Backup Channel</a>\n"
        "📢 " + M + "Main Channel</a>")),
    "d18": ("18 · Request Focus", (
        "<b>{original_caption}</b>\n\n"
        "🙋 <u>Movie chahiye? Request karo:</u>\n"
        "💬 {movies_group_at}")),
    "d19": ("19 · Two Columns", (
        "<b>{original_caption}</b>\n\n"
        "📢 " + F("Main", "serif") + " · {main_channel_at}\n"
        "💾 " + F("Backup", "serif") + " · {backup_channel_at}\n"
        "💬 " + F("Group", "serif") + " · {movies_group_at}")),
    "d20": ("20 · Compact", (
        "🎬 {original_caption}\n"
        "📢 {main_channel_at} ┃ 💾 {backup_channel_at}")),
}
