"""Fixed caption settings (edit this file to change links or design, then redeploy).
Old promo links listed in OLD_LINKS are stripped from captions before the new footer is added."""
from utils.captions import ROAROIC_LINKS, ROAROIC_TEMPLATE

LINKS: dict = dict(ROAROIC_LINKS)
TEMPLATE: str = ROAROIC_TEMPLATE
OLD_LINKS: list = []          # e.g. ["https://t.me/oldchannel", "@oldchannel"]
