from utils import store
from utils.captions import build_caption


def compute_caption(original_html: str, file_name: str | None, chat_id=None) -> str:
    """Caption for one chat: its own template/links when set in the menu, otherwise the defaults."""
    eff = store.effective(chat_id)
    return build_caption(original_html, eff["template"], eff["links"], eff["old_links"], file_name)
