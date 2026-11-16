import settings
from utils.captions import build_caption


def compute_caption(original_html: str, file_name: str | None) -> str:
    return build_caption(original_html, settings.TEMPLATE, settings.LINKS, settings.OLD_LINKS, file_name)
