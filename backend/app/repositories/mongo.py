"""MongoDB access layer (Motor). Works against MongoDB, Atlas, or Azure Cosmos DB for MongoDB vCore."""
from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel

from app.core.logging import get_logger

log = get_logger("mongo")

COLLECTIONS = [
    "matches", "match_events", "players", "teams", "formations", "tactical_patterns", "player_statistics",
    "team_statistics", "historical_matches", "football_memories", "fan_profiles", "agent_runs", "agent_results",
    "insights", "embeddings", "voice_sessions", "visualization_commands", "knowledge_documents", "audit_logs",
]

INDEXES: dict[str, list[IndexModel]] = {
    "matches": [IndexModel([("match_id", ASCENDING)], unique=True), IndexModel([("tenant_id", ASCENDING), ("status", ASCENDING)])],
    "match_events": [IndexModel([("match_id", ASCENDING), ("seq", ASCENDING)], unique=True),
                     IndexModel([("event_id", ASCENDING)], unique=True),
                     IndexModel([("match_id", ASCENDING), ("type", ASCENDING)]),
                     IndexModel([("match_id", ASCENDING), ("player_id", ASCENDING)])],
    "players": [IndexModel([("player_id", ASCENDING)], unique=True), IndexModel([("team_id", ASCENDING)])],
    "teams": [IndexModel([("team_id", ASCENDING)], unique=True)],
    "tactical_patterns": [IndexModel([("match_id", ASCENDING), ("minute", ASCENDING)]), IndexModel([("type", ASCENDING)])],
    "insights": [IndexModel([("insight_id", ASCENDING)], unique=True),
                 IndexModel([("match_id", ASCENDING), ("minute", ASCENDING), ("second", ASCENDING)]),
                 IndexModel([("match_id", ASCENDING), ("category", ASCENDING)]),
                 IndexModel([("match_id", ASCENDING), ("significance", DESCENDING)])],
    "football_memories": [IndexModel([("memory_id", ASCENDING)], unique=True),
                          IndexModel([("entities", ASCENDING)]), IndexModel([("kind", ASCENDING), ("user_id", ASCENDING)])],
    "fan_profiles": [IndexModel([("tenant_id", ASCENDING), ("user_id", ASCENDING)], unique=True)],
    "agent_runs": [IndexModel([("agent_run_id", ASCENDING)], unique=True),
                   IndexModel([("match_id", ASCENDING), ("created_at", DESCENDING)])],
    "historical_matches": [IndexModel([("doc_id", ASCENDING)], unique=True), IndexModel([("teams", ASCENDING)])],
    "knowledge_documents": [IndexModel([("doc_id", ASCENDING)], unique=True), IndexModel([("kind", ASCENDING)])],
    "embeddings": [IndexModel([("collection", ASCENDING), ("doc_id", ASCENDING)], unique=True)],
    "voice_sessions": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)])],
    "visualization_commands": [IndexModel([("match_id", ASCENDING), ("insight_id", ASCENDING)])],
    "audit_logs": [IndexModel([("tenant_id", ASCENDING), ("at", DESCENDING)])],
}


class Database:
    def __init__(self, db) -> None:
        self.db = db

    def __getattr__(self, name: str):
        if name in COLLECTIONS:
            return self.db[name]
        raise AttributeError(name)

    async def ensure_indexes(self) -> None:
        for coll, idx in INDEXES.items():
            try:
                await self.db[coll].create_indexes(idx)
            except Exception as exc:  # noqa: BLE001
                log.warning("index_create_failed", collection=coll, error=str(exc)[:200])

    async def ensure_vector_indexes(self, backend: str, dims: int) -> None:
        """Production vector indexes. Cosmos DB for MongoDB vCore: HNSW cosmosSearch. Atlas: vectorSearch index."""
        for coll in ("historical_matches", "knowledge_documents", "football_memories"):
            try:
                if backend == "cosmos":
                    await self.db.command({"createIndexes": coll, "indexes": [{
                        "name": f"{coll}_vec", "key": {"embedding": "cosmosSearch"},
                        "cosmosSearchOptions": {"kind": "vector-hnsw", "m": 16, "efConstruction": 64,
                                                "similarity": "COS", "dimensions": dims}}]})
                elif backend == "atlas":
                    await self.db.command({"createSearchIndexes": coll, "indexes": [{
                        "name": f"{coll}_vec", "type": "vectorSearch",
                        "definition": {"fields": [{"type": "vector", "path": "embedding", "numDimensions": dims,
                                                   "similarity": "cosine"}, {"type": "filter", "path": "teams"}]}}]})
                log.info("vector_index_ready", collection=coll, backend=backend)
            except Exception as exc:  # noqa: BLE001 — already exists / not supported
                log.warning("vector_index_skipped", collection=coll, backend=backend, error=str(exc)[:160])

    @staticmethod
    def clean(doc: dict | None) -> dict | None:
        if doc is not None:
            doc.pop("_id", None)
        return doc

    async def find(self, coll: str, query: dict, *, sort: list | None = None, limit: int = 0,
                   projection: dict | None = None) -> list[dict]:
        cur = self.db[coll].find(query, projection or {"_id": 0})
        if sort:
            cur = cur.sort(sort)
        if limit:
            cur = cur.limit(limit)
        return [d async for d in cur]

    async def find_one(self, coll: str, query: dict, projection: dict | None = None) -> dict | None:
        return await self.db[coll].find_one(query, projection or {"_id": 0})

    async def upsert(self, coll: str, query: dict, doc: dict[str, Any]) -> None:
        await self.db[coll].update_one(query, {"$set": doc}, upsert=True)

    async def insert(self, coll: str, doc: dict) -> None:
        await self.db[coll].insert_one(dict(doc))

    async def insert_many(self, coll: str, docs: list[dict]) -> None:
        if docs:
            await self.db[coll].insert_many([dict(d) for d in docs], ordered=False)


async def create_database(uri: str, name: str) -> Database:
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2500, tz_aware=False)
    await client.admin.command("ping")
    db = Database(client[name])
    await db.ensure_indexes()
    log.info("mongo_connected", db=name)
    return db


def create_mock_database(name: str = "football_os_test") -> Database:
    from mongomock_motor import AsyncMongoMockClient
    return Database(AsyncMongoMockClient()[name])
