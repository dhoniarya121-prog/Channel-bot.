"""Helpers shared by the admin-panel plugins."""
from database import settings
from keyboards.common import btn, kb
from utils import router, state, tg
from utils.text import parse_int


def onoff(v) -> str:
    return "✅ ON" if v else "❌ OFF"


def back(to: str = "adm:main", label: str = "⬅️ Back"):
    return [btn(label, to)]


async def ask(cq, action: str, prompt: str, **ctx):
    """Prompt the admin for the next message; the router hands it to `on_input(action)`."""
    state.set_state(cq.from_user.id, action, **ctx)
    await tg.show(cq, f"{prompt}\n\n<i>Or send /cancel to abort.</i>", kb([btn("✖️ Cancel", "adm:x")]))


def number_setting(action: str, key: str, label: str, lo: int, hi: int, back_cb: str, perm: str):
    """Registers the input handler that stores a bounded integer in settings[key]."""
    @router.on_input(action, perm)
    async def _handler(client, message, ctx):
        v = parse_int(message.text, lo, hi) if message.text else None
        if v is None:
            state.set_state(message.from_user.id, action)
            await message.reply_text(f"⚠️ Send a whole number between {lo} and {hi} (or /cancel).")
            return
        await settings.set(key, v)
        await message.reply_text(f"✅ {label} set to <b>{v}</b>.", reply_markup=kb(back(back_cb)))
    return _handler


async def number_prompt(cq, action: str, label: str, current, lo: int, hi: int):
    await ask(cq, action, f"✏️ <b>{label}</b>\nCurrent: <b>{current}</b>\nSend a number ({lo}–{hi}):")
