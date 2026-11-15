from database import channels
from keyboards.common import btn, kb
from utils.i18n import t


def main_menu(lang: str, verified: bool, admin: bool):
    rows = [[btn(t(lang, "m_profile"), "u:profile"), btn(t(lang, "m_files"), "u:files:0")],
            [btn(t(lang, "m_submit"), "u:submit"), btn(t(lang, "m_search"), "u:search")],
            [btn(t(lang, "m_request"), "u:request"), btn(t(lang, "m_ref"), "u:ref")],
            [btn(t(lang, "m_prem"), "u:prem"), btn(t(lang, "m_fb"), "u:fb")],
            [btn(t(lang, "m_lang"), "u:lang"), btn(t(lang, "m_help"), "u:help")]]
    if not verified:
        rows.insert(0, [btn(t(lang, "verify"), "v:go")])
    if admin:
        rows.append([btn(t(lang, "m_admin"), "adm:main")])
    return kb(*rows)


def home_btn(lang: str):
    return kb([btn(t(lang, "back"), "u:home")])


def lang_kb():
    return kb([btn("🇬🇧 English", "lang:en"), btn("🇮🇳 हिन्दी", "lang:hi")])


def fsub_kb(lang: str, missing: list[dict], payload: str = ""):
    rows = []
    for ch in missing:
        url = channels.join_url(ch)
        if url:
            rows.append([btn(f"{t(lang, 'join')} {ch.get('title', '')}"[:60], url=url)])
    rows.append([btn(t(lang, "refresh"), f"fs:r:{payload}" if payload else "fs:r")])
    return kb(*rows)


def get_link_kb(lang: str, token: str):
    return kb([btn(t(lang, "get_link"), f"sh:get:{token}")])
