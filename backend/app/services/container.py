"""Service container + the real-time event pipeline (fast path → deep path)."""
from __future__ import annotations

import asyncio
import time

from app.agents.router import score_event
from app.cag.context import ContextCache, compact_event
from app.cag.store import JsonKV, MemoryKV, create_kv
from app.core.config import Settings
from app.core.logging import get_logger
from app.data.knowledge import DEMO_FANS, SEED_MEMORIES, knowledge_documents
from app.data.teams import PLAYERS, TEAMS
from app.graph.builder import build_graphs, new_run_id
from app.llm.router import ModelRouter
from app.mag.memory import MemoryService
from app.models.domain import AgentResult, Insight, Match, MatchEvent
from app.rag.agentic import AgenticRetriever
from app.rag.embeddings import build_embedder
from app.rag.vector_store import VectorStore
from app.repositories.mongo import Database, create_database, create_mock_database
from app.services.broadcaster import create_broadcaster
from app.services.observability import OBS
from app.services.runtime import MatchRuntime
from app.services.story import StoryService
from app.services.tracing import span
from app.voice.speech import SpeechService
from app.workers.pool import WorkerPool

log = get_logger("container")


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runtimes: dict[str, MatchRuntime] = {}
        self.replay_generation: dict[str, int] = {}
        self.db: Database | None = None
        self.ingest_locks: dict[str, asyncio.Lock] = {}
        self.replays: dict = {}

    # ------------------------------------------------------------------ lifecycle
    async def start(self, *, use_mock_db: bool = False, use_memory_kv: bool = False, enable_llm: bool = True) -> None:
        s = self.settings
        if use_mock_db:
            self.db = create_mock_database()
        else:
            try:
                self.db = await create_database(s.mongodb_uri, s.mongodb_db)
            except Exception as exc:  # noqa: BLE001
                log.warning("mongo_unavailable_using_in_memory_mock", error=str(exc)[:200])
                self.db = create_mock_database()
        self.kv = MemoryKV() if use_memory_kv else await create_kv(s.redis_url)
        self.json_kv = JsonKV(self.kv)
        self.cag = ContextCache(self.json_kv, s.context_ttl_seconds)
        self.embedder = build_embedder(s, self.kv)
        self.vectors = VectorStore(self.db, self.embedder, s.vector_backend)
        if s.vector_backend in ("cosmos", "atlas"):
            await self.db.ensure_vector_indexes(s.vector_backend, self.embedder.dim)
        self.retriever = AgenticRetriever(self.vectors)
        self.memory = MemoryService(self.db, self.vectors)
        self.llm = ModelRouter(s if enable_llm else s.model_copy(update={"azure_openai_api_key": ""}), self.json_kv)
        self.speech = SpeechService(s)
        self.broadcaster = create_broadcaster()
        self.story_service = StoryService(self.llm)
        from app.voice.translate import Translator
        self.translator = Translator(self.llm, self.json_kv)
        from app.services.recap import RecapService
        self.recap_service = RecapService(self.llm, self.speech, self.translator)
        from app.services.coach_report import CoachReportService
        from app.services.agent_desk import AgentDesk
        self.coach_report_service = CoachReportService(self.llm)
        self.agent_desk = AgentDesk(self.coach_report_service)
        self.pool = WorkerPool(s.worker_concurrency)
        self.pool.start()
        self.event_graph, self.query_graph = build_graphs(self)
        await self.seed()
        log.info("container_started", llm=self.llm.enabled, speech=self.speech.enabled, kv=self.kv.backend)

    async def stop(self) -> None:
        await self.pool.stop()
        await self.kv.close()

    async def seed(self) -> None:
        """Idempotent reference data + knowledge base + memories + demo fans."""
        for t in TEAMS.values():
            await self.db.upsert("teams", {"team_id": t.team_id}, t.model_dump())
        for p in PLAYERS.values():
            await self.db.upsert("players", {"player_id": p.player_id}, p.model_dump())
        docs = knowledge_documents()
        hist = [d for d in docs if d["collection"] == "historical_matches"]
        lib = [d for d in docs if d["collection"] == "knowledge_documents"]
        await self.vectors.index_documents("historical_matches", hist)
        await self.vectors.index_documents("knowledge_documents", lib)
        for m in SEED_MEMORIES:
            await self.memory.remember(**{k: m[k] for k in ("kind", "text", "entities", "source", "importance")},
                                       user_id=m.get("user_id"), memory_id=m["memory_id"])
        for f in DEMO_FANS:
            await self.db.upsert("fan_profiles", {"tenant_id": "demo", "user_id": f["user_id"]}, {**f, "tenant_id": "demo"})

    # ------------------------------------------------------------------ fan-out
    async def broadcast(self, match_id: str | None, message: dict) -> None:
        if match_id:
            await self.broadcaster.send(match_id, message)

    async def publish_agent_status(self, match_id: str | None, r: AgentResult, run_id: str | None) -> None:
        if not match_id or not self.broadcaster.subscribers(match_id):
            return
        await self.broadcast(match_id, {"type": "agent_status", "run_id": run_id, "agent": r.agent, "status": r.status,
                                        "latency_ms": round(r.latency_ms, 1), "confidence": r.confidence, "model": r.model,
                                        "tokens": r.tokens, "evidence": len(r.evidence_event_ids), "error": r.error})

    async def publish_insight(self, rt: MatchRuntime, insight: Insight) -> None:
        rt.insights.append(insight)
        doc = insight.model_dump()
        await self.db.upsert("insights", {"insight_id": insight.insight_id}, doc)
        if insight.visualization:
            await self.db.upsert("visualization_commands", {"insight_id": insight.insight_id},
                                 {"match_id": rt.match_id, "insight_id": insight.insight_id, "commands": insight.visualization})
        OBS.incr("insights_published")
        await self.broadcast(rt.match_id, {"type": "insight", "insight": doc})

    # ------------------------------------------------------------------ matches
    async def create_match(self, match: Match, reset: bool = True) -> MatchRuntime:
        if reset or match.match_id not in self.runtimes:
            self.runtimes[match.match_id] = MatchRuntime(match)
            self.replay_generation[match.match_id] = self.replay_generation.get(match.match_id, 0) + 1
            await self.kv.delete(ContextCache.key(match.match_id))
        await self.db.upsert("matches", {"match_id": match.match_id}, match.model_dump())
        return self.runtimes[match.match_id]

    # ------------------------------------------------------------------ event pipeline
    async def ingest(self, event: MatchEvent, *, deep: bool = True, persist: bool = True) -> dict:
        """FAST PATH (ordered, ~1 ms): engine update → pattern tracking → CAG → broadcast → significance.
        DEEP PATH (async, pooled): LangGraph run for significant events only."""
        rt = self.runtimes[event.match_id]
        lock = self.ingest_locks.setdefault(event.match_id, asyncio.Lock())
        async with lock:
            delta = rt.engine.update(event)
            changes = rt.patterns.update(rt.engine)
            OBS.incr("events_ingested")
            eng = rt.engine
            sig, cat, reasons = score_event(event, delta, changes, event.minute, eng.score[eng.home] - eng.score[eng.away])
            if persist:
                await self.db.upsert("match_events", {"event_id": event.event_id}, event.model_dump())
                for kind, p in changes:
                    await self.db.insert("tactical_patterns", {**p.to_dict(), "match_id": rt.match_id, "minute": event.minute,
                                                               "transition": kind, "at": time.time()})
            rt.events_since_refresh += 1
            full = rt.events_since_refresh >= 10 or sig >= self.settings.significance_threshold
            if full:
                rt.events_since_refresh = 0
            ctx = await self.cag.refresh(rt, full=full)
            if rt.match.status != "live" and event.type.value not in ("FULL_TIME",):
                rt.match.status = "live"
            if event.type.value == "FULL_TIME":
                rt.match.status = "finished"
                await self.db.upsert("matches", {"match_id": rt.match_id}, {"status": "finished", "score": dict(eng.score)})
            if self.broadcaster.subscribers(rt.match_id):
                msg = {"type": "event", "event": {**compact_event(event), "positions": [p.model_dump() for p in event.positions],
                                                  "meta": event.meta, "related_player_id": event.related_player_id},
                       "score": dict(eng.score), "momentum": eng.momentum_index(), "significance": sig, "category": cat}
                if changes:
                    msg["pattern_changes"] = [{"kind": k, **p.to_dict()} for k, p in changes]
                if full:
                    msg["context"] = {k: ctx.get(k) for k in ("last_5_min", "totals", "active_patterns", "formations", "version")}
                await self.broadcast(rt.match_id, msg)

        # Coalescing: a quick burst of moderately significant events is analysed once.
        game_t = event.game_seconds
        threshold = self.settings.significance_threshold
        new_patterns = [p.to_dict() for kind, p in changes if kind == "start"]
        ended = [p.to_dict() for kind, p in changes if kind == "end"]
        if ended and not new_patterns and cat == "ROUTINE":
            cat = "TACTICAL_SHIFT"
        worth = (cat != "ROUTINE" or sig >= 0.4) and not (event.type.value == "SHOT" and event.outcome == "goal")
        if deep and worth and sig >= threshold and (sig >= 0.6 or game_t - rt.last_deep_t >= 20):
            rt.last_deep_t = game_t
            OBS.incr("events_analysed")
            gen = self.replay_generation.get(rt.match_id, 0)
            key = f"{rt.match_id}:{gen}:{event.event_id}"
            state = {"run_id": new_run_id(), "mode": "event", "match_id": rt.match_id, "timestamp": time.time(),
                     "event_obj": event, "event_delta": delta, "pattern_changes": changes, "new_patterns": new_patterns,
                     "ended_patterns": ended, "frozen": {"score": dict(eng.score), "clock": event.clock,
                                                          "active_patterns": rt.patterns.active_list()},
                     "significance": sig, "category": cat, "reasons": reasons, "agent_results": {}, "graph_path": []}
            self.pool.submit(key, sig, lambda st=state: self.run_event_graph(st), max_age_s=45)
        elif sig < threshold:
            OBS.incr("events_fast_path_only")
        else:
            OBS.incr("events_coalesced")
        return {"significance": sig, "category": cat, "reasons": reasons, "patterns": [k for k, _ in changes]}

    async def run_event_graph(self, state: dict) -> dict:
        t0 = time.perf_counter()
        await self.broadcast(state["match_id"], {"type": "run_started", "run_id": state["run_id"],
                                                 "event_id": state["event_obj"].event_id, "significance": state["significance"],
                                                 "category": state["category"], "reasons": state["reasons"]})
        with span("langgraph.event", match_id=state["match_id"], run_id=state["run_id"],
                  event_id=state["event_obj"].event_id, category=state["category"]):
            out = await self.event_graph.ainvoke(state)
        dur = round((time.perf_counter() - t0) * 1000, 1)
        tokens = sum(r.get("tokens", 0) for r in out.get("agent_results", {}).values())
        await self.db.insert("agent_runs", {"agent_run_id": state["run_id"], "match_id": state["match_id"],
                                            "event_id": state["event_obj"].event_id, "graph_path": out.get("graph_path", []),
                                            "duration_ms": dur, "tokens": tokens, "model_tier": out.get("model_tier"),
                                            "cache_hit": out.get("cache_hit", False), "created_at": time.time(),
                                            "agents": {k: {"status": v.get("status"), "latency_ms": round(v.get("latency_ms", 0), 1),
                                                           "confidence": v.get("confidence"), "tokens": v.get("tokens", 0)}
                                                       for k, v in out.get("agent_results", {}).items()}})
        await self.broadcast(state["match_id"], {"type": "run_complete", "run_id": state["run_id"], "duration_ms": dur,
                                                 "tokens": tokens, "graph_path": out.get("graph_path", []),
                                                 "cache_hit": out.get("cache_hit", False)})
        OBS.incr("graph_runs")
        return out

    async def ask(self, match_id: str, question: str, *, user_id: str | None = None, persona: str | None = None,
                  level: str | None = None, tenant_id: str = "demo", language: str = "en") -> dict:
        """Fan Q&A. Non-English questions are translated in, answered by the graph, and translated back (verified)."""
        original = question
        if language and not language.startswith("en"):
            question = await self._to_english(question)
        profile = await self.db.find_one("fan_profiles", {"tenant_id": tenant_id, "user_id": user_id}) if user_id else None
        state = {"run_id": new_run_id(), "mode": "query", "match_id": match_id, "timestamp": time.time(), "question": question[:500],
                 "user_id": user_id, "tenant_id": tenant_id, "profile": profile or {}, "persona": persona, "level": level,
                 "agent_results": {}, "graph_path": []}
        t0 = time.perf_counter()
        with span("langgraph.query", match_id=match_id, run_id=state["run_id"]):
            out = await self.query_graph.ainvoke(state)
        OBS.incr("questions_answered")
        ins = out["final_insight"]
        if language and not language.startswith("en"):
            ins = await self.localize(ins, language, out.get("level") or "intermediate", out.get("persona") or "casual_commentator")
            ins["statistics"]["question_original"] = original
            ins["statistics"]["question_english"] = question
        ins["statistics"]["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        ins["statistics"]["persona"] = out.get("persona")
        return ins

    async def _to_english(self, text: str) -> str:
        res = await self.llm.complete_json(
            system="Translate the user's football question into English. Return JSON {\"en\": \"...\"}. Keep names as written.",
            user=text, tier="small", fallback=lambda: {"en": text}, max_tokens=200, temperature=0, interactive=True)
        return str(res.data.get("en") or text)

    async def localize(self, ins: dict, lang: str, level: str, persona: str) -> dict:
        """Translate the fan-facing fields of an insight/answer; numbers and names are re-verified."""
        from app.data.teams import PLAYERS
        stats = ins.get("statistics") or {}
        fields = {"headline": ins.get("headline", ""),
                  "explanation": stats.get("answer") if ins.get("category") == "ANSWER" else (ins.get("explanations") or {}).get(level, ""),
                  "commentary": ins.get("commentary", ""), "historical_note": ins.get("historical_note", ""),
                  "voice": (ins.get("voice_scripts") or {}).get(persona, "")}
        names = [p.name for p in PLAYERS.values()]
        tr = await self.translator.translate(fields, lang, names)
        f = tr["fields"]
        out = dict(ins)
        out["localized"] = {"language": tr["lang"], "verified": tr["verified"], "cached": tr.get("cached", False),
                            "headline": f["headline"], "explanation": f["explanation"], "commentary": f["commentary"],
                            "historical_note": f["historical_note"], "voice": f["voice"] or f["commentary"],
                            "issues": tr.get("issues", [])}
        return out
