"""An in-memory stand-in for the slice of pymongo the Zeus Agents site uses: equality plus ``$gte``,
``$lt``, ``$regex``/``$options`` and ``$or`` filters, include/exclude projections, ``sort``/``limit``
cursors and the write results the server reads (``modified_count``, ``deleted_count``)."""

import re
import types


def matches(doc, query):
    for key, cond in query.items():
        if key == "$or":
            if not any(matches(doc, q) for q in cond):
                return False
        elif isinstance(cond, dict) and any(k.startswith("$") for k in cond):
            if not _ops(doc.get(key), cond):
                return False
        elif doc.get(key) != cond:
            return False
    return True


def _ops(value, cond):
    for op, arg in cond.items():
        if op == "$gte" and not (value is not None and value >= arg):
            return False
        if op == "$lt" and not (value is not None and value < arg):
            return False
        if op == "$regex":
            flags = re.I if "i" in cond.get("$options", "") else 0
            if not (isinstance(value, str) and re.search(arg, value, flags)):
                return False
    return True


def project(doc, projection):
    if not projection:
        return dict(doc)
    included = [k for k, v in projection.items() if v and k != "_id"]
    out = {k: doc[k] for k in included if k in doc} if included else dict(doc)
    if projection.get("_id") == 0:
        out.pop("_id", None)
    elif included and "_id" in doc:
        out["_id"] = doc["_id"]
    return out


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda d: d.get(key) or "", reverse=direction < 0))

    def limit(self, n):
        return Cursor(self[:n])


class Collection:
    def __init__(self):
        self.docs = []
        self._next_id = 1

    def find(self, query=None, projection=None):
        return Cursor(project(d, projection) for d in self.docs if matches(d, query or {}))

    def find_one(self, query, projection=None):
        return next(iter(self.find(query, projection)), None)

    def count_documents(self, query):
        return sum(matches(d, query) for d in self.docs)

    def insert_one(self, doc):
        self.docs.append(dict(doc, _id=self._next_id))
        self._next_id += 1

    def insert_many(self, docs):
        for doc in docs:
            self.insert_one(doc)

    def update_one(self, query, update, upsert=False):
        doc = next((d for d in self.docs if matches(d, query)), None)
        if doc is None:
            if upsert:
                self.insert_one(dict({k: v for k, v in query.items() if not k.startswith("$")},
                                     **update.get("$setOnInsert", {}), **update.get("$set", {})))
            return types.SimpleNamespace(matched_count=0, modified_count=0)
        doc.update(update.get("$set", {}))
        return types.SimpleNamespace(matched_count=1, modified_count=1)

    def update_many(self, query, update):
        hits = [d for d in self.docs if matches(d, query)]
        for doc in hits:
            doc.update(update.get("$set", {}))
        return types.SimpleNamespace(matched_count=len(hits), modified_count=len(hits))

    def delete_one(self, query):
        doc = next((d for d in self.docs if matches(d, query)), None)
        if doc is not None:
            self.docs.remove(doc)
        return types.SimpleNamespace(deleted_count=int(doc is not None))

    def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not matches(d, query)]
        return types.SimpleNamespace(deleted_count=before - len(self.docs))

    def create_index(self, *args, **kwargs):
        pass


class Database:
    """Collections spring into existence on first access, as with ``pymongo.database.Database``."""

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        collection = Collection()
        setattr(self, name, collection)
        return collection

    def command(self, name):
        if name == "dbStats":
            return {"dataSize": 1024, "storageSize": 4096, "indexSize": 512}
        return {"ok": 1}
