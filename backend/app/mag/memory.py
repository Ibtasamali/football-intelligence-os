"""MAG — Memory-Augmented Generation.

Long-term football memory in MongoDB (`football_memories`): team and player history, tactical patterns
seen in earlier matches (including earlier in *this* match), relationships, and per-fan conversation
history and preferences. Recall blends semantic similarity, entity overlap, importance and recency, and
is scoped by tenant/user for personal memories.
"""
from __future__ import annotations

import time

from app.models.domain import new_id
from app.services.observability import OBS

COLL = "football_memories"


class MemoryService:
    def __init__(self, db, vector_store) -> None:
        self.db, self.vs = db, vector_store

    async def remember(self, *, kind: str, text: str, entities: list[str], source: str, importance: float = 0.5,
                       match_id: str | None = None, user_id: str | None = None, tenant_id: str = "demo",
                       memory_id: str | None = None, extra: dict | None = None) -> dict:
        mid = memory_id or new_id("mem")
        doc = {"memory_id": mid, "doc_id": mid, "kind": kind, "text": text, "entities": entities, "source": source,
               "importance": importance, "match_id": match_id, "user_id": user_id, "tenant_id": tenant_id,
               "created_at": time.time(), **(extra or {})}
        await self.vs.index_documents(COLL, [doc])
        OBS.incr("memories_written")
        return doc

    async def recall(self, query: str, *, entities: list[str] | None = None, user_id: str | None = None,
                     kinds: list[str] | None = None, k: int = 4, exclude_match: str | None = None) -> list[dict]:
        entities = entities or []
        hits = await self.vs.search(COLL, query, k=24)
        now = time.time()
        out = []
        for h in hits:
            if h.get("user_id") and h["user_id"] != user_id:
                continue  # personal memories are private to their user
            if kinds and h.get("kind") not in kinds:
                continue
            if exclude_match and h.get("match_id") == exclude_match and h.get("kind") == "match_moment":
                continue
            overlap = len(set(h.get("entities", [])) & set(entities)) / max(1, len(set(entities))) if entities else 0
            personal = 0.25 if user_id and h.get("user_id") == user_id else 0
            age_h = (now - h.get("created_at", now)) / 3600
            recency = 0.1 / (1 + age_h / 24)
            score = 0.45 * h.get("score", 0) + 0.3 * overlap + 0.15 * h.get("importance", 0.5) + recency + personal
            if overlap == 0 and not personal and h.get("score", 0) < 0.2:
                continue
            out.append({"memory_id": h["memory_id"], "kind": h.get("kind"), "text": h["text"], "source": h.get("source"),
                        "entities": h.get("entities", []), "match_id": h.get("match_id"),
                        "minute": h.get("minute"), "score": round(score, 3)})
        OBS.incr("memory_recalls")
        return sorted(out, key=lambda m: -m["score"])[:k]

    async def remember_conversation(self, user_id: str, tenant_id: str, question: str, answer: str,
                                    entities: list[str], match_id: str | None) -> None:
        await self.remember(kind="conversation", text=f"Fan asked: \"{question}\". Answer given: {answer}",
                            entities=entities, source="Fan conversation history", importance=0.6,
                            match_id=match_id, user_id=user_id, tenant_id=tenant_id)
