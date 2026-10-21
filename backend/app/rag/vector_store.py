"""Vector search over MongoDB collections.

backends
  local  — cosine similarity in numpy over vectors stored on the documents (dev / tests)
  atlas  — MongoDB Atlas `$vectorSearch`
  cosmos — Azure Cosmos DB for MongoDB vCore `cosmosSearch` (create a vector-ivf/hnsw index on `embedding`)
"""
from __future__ import annotations

import numpy as np

from app.core.logging import get_logger

log = get_logger("vector")


class VectorStore:
    def __init__(self, db, embedder, backend: str = "local") -> None:
        self.db, self.embedder, self.backend = db, embedder, backend
        self._cache: dict[str, tuple[list[dict], np.ndarray]] = {}

    def invalidate(self, collection: str) -> None:
        self._cache.pop(collection, None)

    async def index_documents(self, collection: str, docs: list[dict], text_field: str = "text") -> int:
        vecs = await self.embedder.embed([d[text_field] for d in docs])
        for d, v in zip(docs, vecs):
            d["embedding"] = v
            d["embedding_model"] = self.embedder.name
            await self.db.upsert(collection, {"doc_id": d["doc_id"]}, d)
        self.invalidate(collection)
        return len(docs)

    async def _load(self, collection: str) -> tuple[list[dict], np.ndarray]:
        if collection not in self._cache:
            docs = await self.db.find(collection, {"embedding": {"$exists": True}})
            mat = np.array([d["embedding"] for d in docs], dtype=np.float32) if docs else np.zeros((0, self.embedder.dim))
            self._cache[collection] = (docs, mat)
        return self._cache[collection]

    async def search(self, collection: str, query: str, k: int = 5, filters: dict | None = None) -> list[dict]:
        qv = (await self.embedder.embed([query]))[0]
        if self.backend == "atlas":
            pipeline = [{"$vectorSearch": {"index": f"{collection}_vec", "path": "embedding", "queryVector": qv,
                                           "numCandidates": k * 10, "limit": k, **({"filter": filters} if filters else {})}},
                        {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "vectorSearchScore"}}}]
            return [d async for d in self.db.db[collection].aggregate(pipeline)]
        if self.backend == "cosmos":
            pipeline = [{"$search": {"cosmosSearch": {"vector": qv, "path": "embedding", "k": k * 2}, "returnStoredSource": True}},
                        {"$project": {"_id": 0, "embedding": 0, "score": {"$meta": "searchScore"}, "doc": "$$ROOT"}}]
            rows = [d async for d in self.db.db[collection].aggregate(pipeline)]
            rows = [{**r.get("doc", r), "score": r["score"]} for r in rows]
            return [r for r in rows if _match(r, filters)][:k]
        docs, mat = await self._load(collection)
        if not docs:
            return []
        sims = mat @ np.array(qv, dtype=np.float32)
        order = np.argsort(-sims)
        out = []
        for i in order:
            d = docs[int(i)]
            if not _match(d, filters):
                continue
            out.append({**{kk: vv for kk, vv in d.items() if kk != "embedding"}, "score": round(float(sims[int(i)]), 4)})
            if len(out) >= k:
                break
        return out


def _match(doc: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    for key, val in filters.items():
        dv = doc.get(key)
        if isinstance(val, dict) and "$in" in val:
            options = val["$in"]
            if isinstance(dv, list):
                if not set(dv) & set(options):
                    return False
            elif dv not in options:
                return False
        elif isinstance(dv, list):
            if val not in dv:
                return False
        elif dv != val:
            return False
    return True
