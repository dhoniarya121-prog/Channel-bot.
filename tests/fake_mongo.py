"""Minimal in-memory emulator of the Motor API subset this project uses.
Every operation yields to the event loop first (so concurrent tasks interleave) and then executes
atomically, like a single-document MongoDB operation. It is NOT a substitute for real MongoDB:
run the suite with TEST_MONGO_URI to verify against the real server."""
import asyncio
import copy
import pickle
import re
import uuid

try:
    from pymongo.errors import DuplicateKeyError
except ImportError:  # pragma: no cover
    class DuplicateKeyError(Exception):
        pass

MISSING = object()


def _get(doc, path):
    cur = doc
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return MISSING
    return cur


def _set(doc, path, value):
    parts = path.split(".")
    for p in parts[:-1]:
        doc = doc.setdefault(p, {})
    doc[parts[-1]] = value


def _unset(doc, path):
    parts = path.split(".")
    for p in parts[:-1]:
        doc = doc.get(p, {})
    doc.pop(parts[-1], None)


def _eq(val, target):
    if val is MISSING:
        return target is None
    if isinstance(val, list) and not isinstance(target, list):
        return target in val
    return val == target


def _cmp(val, arg, fn):
    if val is MISSING or val is None:
        return False
    try:
        return fn(val, arg)
    except TypeError:
        return False


def _cond(val, cond):
    if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$ne":
                if _eq(val, arg):
                    return False
            elif op == "$gt":
                if not _cmp(val, arg, lambda a, b: a > b): return False
            elif op == "$gte":
                if not _cmp(val, arg, lambda a, b: a >= b): return False
            elif op == "$lt":
                if not _cmp(val, arg, lambda a, b: a < b): return False
            elif op == "$lte":
                if not _cmp(val, arg, lambda a, b: a <= b): return False
            elif op == "$in":
                if not any(_eq(val, a) for a in arg): return False
            elif op == "$exists":
                if (val is not MISSING) != bool(arg): return False
            elif op == "$regex":
                flags = re.I if "i" in cond.get("$options", "") else 0
                if val is MISSING or not isinstance(val, str) or not re.search(arg, val, flags): return False
            elif op == "$options":
                continue
            else:
                raise NotImplementedError(op)
        return True
    return _eq(val, cond)


def _match(doc, flt):
    for k, v in (flt or {}).items():
        if k == "$or":
            if not any(_match(doc, f) for f in v): return False
        elif k == "$and":
            if not all(_match(doc, f) for f in v): return False
        elif not _cond(_get(doc, k), v):
            return False
    return True


def _apply(doc, upd, inserting=False):
    for op, spec in upd.items():
        if op == "$set":
            for k, v in spec.items(): _set(doc, k, copy.deepcopy(v))
        elif op == "$unset":
            for k in spec: _unset(doc, k)
        elif op == "$inc":
            for k, v in spec.items():
                cur = _get(doc, k)
                _set(doc, k, (0 if cur is MISSING else cur) + v)
        elif op == "$push":
            for k, v in spec.items():
                cur = _get(doc, k)
                if cur is MISSING: _set(doc, k, [copy.deepcopy(v)])
                else: cur.append(copy.deepcopy(v))
        elif op == "$addToSet":
            for k, v in spec.items():
                cur = _get(doc, k)
                if cur is MISSING: _set(doc, k, [v])
                elif v not in cur: cur.append(v)
        elif op == "$setOnInsert":
            if inserting:
                for k, v in spec.items(): _set(doc, k, copy.deepcopy(v))
        else:
            raise NotImplementedError(op)


class _Res:
    def __init__(self, **kw):
        self.matched_count = kw.get("matched", 0)
        self.modified_count = kw.get("modified", 0)
        self.upserted_id = kw.get("upserted")
        self.inserted_id = kw.get("inserted")
        self.deleted_count = kw.get("deleted", 0)


class Cursor:
    def __init__(self, docs, projection=None):
        self._docs, self._proj = docs, projection
        self._skip = self._limit = 0

    def sort(self, key, direction=1):
        keys = key if isinstance(key, list) else [(key, direction)]
        for k, d in reversed(keys):
            self._docs.sort(key=lambda x: (_get(x, k) is MISSING, _get(x, k) if _get(x, k) is not MISSING else 0),
                            reverse=(d == -1))
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _final(self):
        d = self._docs[self._skip:]
        if self._limit:
            d = d[: self._limit]
        out = []
        for x in d:
            if self._proj:
                inc = {k for k, v in self._proj.items() if v and k != "_id"}
                x = {k: v for k, v in x.items() if k == "_id" or k in inc}
            out.append(copy.deepcopy(x))
        return out

    async def to_list(self, length=None):
        await asyncio.sleep(0)
        r = self._final()
        return r if not length else r[:length]

    def __aiter__(self):
        async def gen():
            await asyncio.sleep(0)
            for x in self._final():
                yield x
        return gen()


class Collection:
    def __init__(self, name):
        self.name = name
        self.docs: dict = {}
        self.unique: list[list[str]] = []

    async def create_index(self, keys, unique=False, **kw):
        await asyncio.sleep(0)
        if unique:
            ks = [k for k, _ in keys] if isinstance(keys, list) else [keys]
            if ks not in self.unique:
                self.unique.append(ks)

    def _check_unique(self, doc, own_id=None):
        for ks in self.unique:
            vals = [_get(doc, k) for k in ks]
            if any(v is MISSING for v in vals):
                continue
            for other in self.docs.values():
                if other["_id"] != own_id and [_get(other, k) for k in ks] == vals:
                    raise DuplicateKeyError(f"E11000 duplicate key on {self.name}: {ks}")

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        doc = copy.deepcopy(doc)
        doc.setdefault("_id", uuid.uuid4().hex)
        if doc["_id"] in self.docs:
            raise DuplicateKeyError(f"E11000 duplicate _id in {self.name}")
        self._check_unique(doc)
        self.docs[doc["_id"]] = doc
        return _Res(inserted=doc["_id"])

    async def find_one(self, flt=None, projection=None, sort=None):
        await asyncio.sleep(0)
        rows = [d for d in self.docs.values() if _match(d, flt)]
        if sort:
            rows = Cursor(rows).sort(sort)._docs
        return copy.deepcopy(rows[0]) if rows else None

    def find(self, flt=None, projection=None):
        return Cursor([d for d in self.docs.values() if _match(d, flt)], projection)

    async def count_documents(self, flt=None):
        await asyncio.sleep(0)
        return sum(1 for d in self.docs.values() if _match(d, flt))

    def _upsert_base(self, flt):
        base = {}
        for k, v in (flt or {}).items():
            if k.startswith("$"):
                continue
            if isinstance(v, dict) and v and all(x.startswith("$") for x in v):
                continue
            _set(base, k, copy.deepcopy(v))
        return base

    async def _update(self, flt, upd, upsert, many=False, want_doc=None):
        await asyncio.sleep(0)
        targets = [d for d in self.docs.values() if _match(d, flt)]
        if not many:
            targets = targets[:1]
        if not targets:
            if not upsert:
                return _Res(), None, None
            doc = self._upsert_base(flt)
            _apply(doc, upd, inserting=True)
            doc.setdefault("_id", uuid.uuid4().hex)
            if doc["_id"] in self.docs:
                raise DuplicateKeyError(f"E11000 duplicate _id in {self.name}")
            self._check_unique(doc)
            self.docs[doc["_id"]] = doc
            return _Res(upserted=doc["_id"]), None, copy.deepcopy(doc)
        before, after, modified = None, None, 0
        for d in targets:
            new = copy.deepcopy(d)
            _apply(new, upd)
            self._check_unique(new, own_id=d["_id"])
            if new != d:
                modified += 1
            before, after = copy.deepcopy(d), copy.deepcopy(new)
            self.docs[d["_id"]] = new
        return _Res(matched=len(targets), modified=modified), before, after

    async def update_one(self, flt, upd, upsert=False):
        return (await self._update(flt, upd, upsert))[0]

    async def update_many(self, flt, upd, upsert=False):
        return (await self._update(flt, upd, upsert, many=True))[0]

    async def find_one_and_update(self, flt, upd, upsert=False, return_document=False, **kw):
        _, before, after = await self._update(flt, upd, upsert)
        return after if return_document else before

    async def delete_one(self, flt):
        await asyncio.sleep(0)
        for d in list(self.docs.values()):
            if _match(d, flt):
                del self.docs[d["_id"]]
                return _Res(deleted=1)
        return _Res(deleted=0)

    async def delete_many(self, flt):
        await asyncio.sleep(0)
        gone = [d["_id"] for d in self.docs.values() if _match(d, flt)]
        for i in gone:
            del self.docs[i]
        return _Res(deleted=len(gone))


class FakeDB:
    def __init__(self, path=None):
        self.cols: dict[str, Collection] = {}
        self.path = path
        if path:
            try:
                with open(path, "rb") as f:
                    for name, docs in pickle.load(f).items():
                        self[name].docs = docs
            except FileNotFoundError:
                pass

    def __getitem__(self, name):
        return self.cols.setdefault(name, Collection(name))

    async def command(self, cmd):
        await asyncio.sleep(0)
        return {"ok": 1}

    def save(self):
        with open(self.path, "wb") as f:
            pickle.dump({n: c.docs for n, c in self.cols.items()}, f)
