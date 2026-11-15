"""MongoDB JSON backup (gzip). Restore is intentionally not automated: restore with mongoimport."""
import gzip
import json
import os
import tempfile
import time

from database import mongo

MAX_SEND = 49 * 1024 * 1024
SKIP = {mongo.LOGS}


def _default(o):
    return o.isoformat() if hasattr(o, "isoformat") else str(o)


async def create_backup() -> list[tuple[str, int]]:
    """Returns [(path, doc_count)] - one combined file, or one file per collection if too large."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    data, counts = {}, {}
    for name in mongo.ALL_COLLECTIONS:
        if name in SKIP:
            continue
        docs = await mongo.col(name).find({}).to_list(None)
        data[name], counts[name] = docs, len(docs)
    d = tempfile.mkdtemp(prefix="roaroic_bk_")
    combined = os.path.join(d, f"roaroic_backup_{stamp}.json.gz")
    with gzip.open(combined, "wt", encoding="utf-8") as f:
        json.dump(data, f, default=_default)
    if os.path.getsize(combined) <= MAX_SEND:
        return [(combined, sum(counts.values()))]
    os.remove(combined)
    out = []
    for name, docs in data.items():
        p = os.path.join(d, f"{name}_{stamp}.json.gz")
        with gzip.open(p, "wt", encoding="utf-8") as f:
            json.dump(docs, f, default=_default)
        out.append((p, counts[name]))
    return out
