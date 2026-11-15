"""Referral program: user link/stats + admin controls."""
import logging

from pyrogram import Client, filters

from database import referrals, settings, users
from keyboards.common import btn, kb
from keyboards.user import home_btn
from utils import adminui, router, tg
from utils.adminui import back, onoff
from utils.i18n import t
from utils.links import referral_link
from utils.text import esc, trunc

log = logging.getLogger(__name__)


async def reward_text(lang: str) -> str:
    q, d = await settings.get("referral_reward_quota"), await settings.get("referral_reward_premium_days")
    key = "ref_reward_daily" if await settings.get("quota_mode") == "daily" else "ref_reward_quota"
    parts = ([t(lang, key, n=q)] if q else []) + ([t(lang, "ref_reward_days", n=d)] if d else [])
    return ", ".join(parts) or "—"


async def referral_view(client, doc: dict):
    lang = doc.get("lang", "en")
    if not await settings.get("referral_enabled"):
        return t(lang, "ref_off")
    code = await referrals.ensure_code(doc["_id"])
    st = await referrals.stats(doc["_id"])
    return t(lang, "ref_info", link=referral_link(await tg.bot_username(client), code),
             reward=await reward_text(lang), **st)


@Client.on_message(filters.command(["referral", "invite"]) & filters.private)
async def referral_cmd(client, message):
    doc = await users.get(message.from_user.id)
    await message.reply_text(await referral_view(client, doc), reply_markup=home_btn(doc.get("lang", "en")))


@router.cb("u:ref")
async def cb_user_ref(client, cq, args):
    doc = await users.get(cq.from_user.id)
    await tg.show(cq, await referral_view(client, doc), home_btn(doc.get("lang", "en")))


# ------------------------------------------------------------------- admin
adminui.number_setting("adm_rf_rq", "referral_reward_quota", "Reward shares per referral", 0, 100, "adm:rf", "referrals")
adminui.number_setting("adm_rf_rp", "referral_reward_premium_days", "Reward premium days per referral", 0, 365, "adm:rf", "referrals")
adminui.number_setting("adm_rf_cap", "referral_daily_cap", "Daily referral cap per referrer (0 = unlimited)", 0, 1000, "adm:rf", "referrals")


@router.cb("adm:rf", "referrals")
async def adm_referrals(client, cq, args):
    s = {k: await settings.get(k) for k in ("referral_enabled", "referral_reward_quota",
                                            "referral_reward_premium_days", "referral_daily_cap")}
    await tg.show(cq, "🎁 <b>Referral Management</b>\n\n"
                      f"Program: {onoff(s['referral_enabled'])}\nReward shares: <b>{s['referral_reward_quota']}</b>\n"
                      f"Reward premium days: <b>{s['referral_reward_premium_days']}</b>\n"
                      f"Daily cap per referrer: <b>{s['referral_daily_cap']}</b> (anti-abuse)\n\n"
                      "Rewards are paid once, after the referred user verifies.",
                  kb([btn(f"🔘 Program: {onoff(s['referral_enabled'])}", "adm:rf:tog")],
                     [btn("🎁 Reward shares", "adm:rf:rq"), btn("💎 Reward days", "adm:rf:rp")],
                     [btn("🛡 Daily cap", "adm:rf:cap"), btn("🏆 Top referrers", "adm:rf:top")], back()))


@router.cb("adm:rf:tog", "referrals")
async def adm_ref_toggle(client, cq, args):
    await settings.toggle("referral_enabled")
    await adm_referrals(client, cq, args)


@router.cb("adm:rf:rq", "referrals")
async def adm_ref_rq(client, cq, args):
    await adminui.number_prompt(cq, "adm_rf_rq", "Reward shares per referral", await settings.get("referral_reward_quota"), 0, 100)


@router.cb("adm:rf:rp", "referrals")
async def adm_ref_rp(client, cq, args):
    await adminui.number_prompt(cq, "adm_rf_rp", "Reward premium days per referral", await settings.get("referral_reward_premium_days"), 0, 365)


@router.cb("adm:rf:cap", "referrals")
async def adm_ref_cap(client, cq, args):
    await adminui.number_prompt(cq, "adm_rf_cap", "Daily referral cap per referrer (0 = unlimited)", await settings.get("referral_daily_cap"), 0, 1000)


@router.cb("adm:rf:top", "referrals")
async def adm_ref_top(client, cq, args):
    rows = await referrals.top(10)
    lines = ["🏆 <b>Top referrers</b>", ""] + [
        f"{i}. {esc(trunc(u.get('first_name'), 24))} (<code>{u['_id']}</code>) — {u.get('referral_count', 0)}"
        for i, u in enumerate(rows, 1)] if rows else ["🏆 <b>Top referrers</b>", "", "No rewarded referrals yet."]
    await tg.show(cq, "\n".join(lines), kb(back("adm:rf")))
