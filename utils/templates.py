"""Caption template presets selectable from the bot menu."""
from utils import captions as C

PRESETS = {
    "roaroic": "🔥 ROAROIC Full",
    "roaroic_simple": "✨ ROAROIC Simple",
    "quote": "📝 Quote list",
    "default": "🎬 Classic",
    "minimal": "▫️ Minimal",
}
CUSTOM = "custom"


def name(key: str | None) -> str:
    return "✍️ Custom" if key == CUSTOM else PRESETS.get(key or "", "🔥 ROAROIC Full")


def resolve(key: str | None, custom: str, links: dict) -> str:
    """Template text for a preset key (or the custom text when it is set)."""
    if key == CUSTOM and (custom or "").strip():
        return custom
    if key == "quote":
        return C.build_quote_template(list(links))
    return {
        "roaroic": C.ROAROIC_TEMPLATE,
        "roaroic_simple": C.ROAROIC_SIMPLE_TEMPLATE,
        "default": C.DEFAULT_TEMPLATE,
        "minimal": C.MINIMAL_TEMPLATE,
    }.get(key or "", C.ROAROIC_TEMPLATE)
