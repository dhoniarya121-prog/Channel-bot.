"""Text styles that work everywhere in Telegram (button labels cannot use HTML, so unicode letters are used).
Only A-Z, a-z, 0-9 are changed; emojis and symbols stay as they are."""

_SMALL_CAPS = dict(zip("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"))

# name -> (first upper-case code point, first lower-case code point, first digit code point or None)
_BLOCKS = {
    "bold": (0x1D5D4, 0x1D5EE, 0x1D7EC),        # 𝗕𝗼𝗹𝗱 sans
    "italic": (0x1D608, 0x1D622, None),          # 𝘐𝘵𝘢𝘭𝘪𝘤 sans
    "mono": (0x1D670, 0x1D68A, 0x1D7F6),         # 𝙼𝚘𝚗𝚘
    "serif": (0x1D400, 0x1D41A, 0x1D7CE),        # 𝐁𝐨𝐥𝐝 serif
    "script": (0x1D4D0, 0x1D4EA, None),          # 𝓢𝓬𝓻𝓲𝓹𝓽
}
FONTS = {"normal": "Aa", "bold": "𝗔𝗮", "small": "ꜱᴍ", "mono": "𝙼𝚘"}     # fonts offered for button labels


def fancy(text: str, style: str) -> str:
    if style in (None, "", "normal"):
        return text
    if style in ("small", "smallcaps"):
        return "".join(_SMALL_CAPS.get(c.lower(), c) if c.isascii() and c.isalpha() else c for c in text)
    up, lo, dg = _BLOCKS.get(style, (None, None, None))
    if up is None:
        return text
    out = []
    for c in text:
        if "A" <= c <= "Z":
            out.append(chr(up + ord(c) - 65))
        elif "a" <= c <= "z":
            out.append(chr(lo + ord(c) - 97))
        elif "0" <= c <= "9" and dg:
            out.append(chr(dg + ord(c) - 48))
        else:
            out.append(c)
    return "".join(out)
