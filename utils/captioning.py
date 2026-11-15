from database import settings
from utils.captions import build_caption


async def compute_caption(original_html: str, file_name: str | None) -> str:
    templates = await settings.get("caption_templates")
    tpl = templates.get(await settings.get("active_template")) or next(iter(templates.values()))
    return build_caption(original_html, tpl, await settings.get("links"), await settings.get("old_links"), file_name)
