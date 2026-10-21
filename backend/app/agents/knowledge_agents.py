"""Knowledge agents: CAG context, MAG memory, Agentic RAG, historical comparison, similar moments."""
from __future__ import annotations

from app.agents.base import Agent, AgentContext
from app.data.teams import team_name
from app.rag.agentic import RetrievalRequest


class CAGContextAgent(Agent):
    name, family = "cag_context", "knowledge"
    description = "Reads the live match context cache instead of re-querying the database."

    async def execute(self, ctx: AgentContext):
        c = await ctx.services.cag.get(ctx.runtime.match_id)
        if not c:
            c = await ctx.services.cag.refresh(ctx.runtime)
            return {"cache": "miss→refreshed", "version": c["version"], "score_text": c["score_text"]}, 0.7, []
        return {"cache": "hit", "version": c["version"], "score_text": c["score_text"], "clock": c["clock"],
                "active_patterns": [p["type"] for p in c.get("active_patterns", [])],
                "last_5_min": c.get("last_5_min"), "age_s": None}, 0.95, []


class MAGMemoryAgent(Agent):
    name, family = "mag_memory", "knowledge"
    description = "Recalls long-term football memories and the fan's own history."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        entities = list(dict.fromkeys((st.get("team_ids") or []) + (st.get("player_ids") or [])))
        patterns = [p["type"] for p in st.get("new_patterns", [])] + [p["type"] for p in ctx.runtime.patterns.active_list()]
        query = " ".join([st.get("question") or "", " ".join(p.replace("_", " ").lower() for p in patterns),
                          ctx.state.get("event_summary", "")])
        mems = await ctx.services.memory.recall(query, entities=entities, user_id=st.get("user_id"), k=4)
        return {"memories": mems, "query": query.strip()[:200]}, (0.75 if mems else 0.3), []


class RAGRetrievalAgent(Agent):
    name, family = "rag_retrieval", "knowledge"
    description = "Agentic RAG: decides if retrieval is needed, plans, retrieves, reranks, validates, re-plans."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        patterns = [p["type"] for p in st.get("new_patterns", [])] or [p["type"] for p in ctx.runtime.patterns.active_list()][:2]
        if st.get("category") == "GOAL" and not patterns:
            patterns = ["GOAL"]
        req = RetrievalRequest(reason=st.get("retrieval_reason", "pattern_start"), teams=st.get("team_ids", []),
                               players=st.get("player_ids", [])[:3], patterns=patterns[:2],
                               question=st.get("question"), intent=st.get("intent"),
                               cached_context_sufficient=st.get("cached_context_sufficient", False))
        res = await ctx.services.retriever.retrieve(req)
        return {"documents": res.documents, "plan": res.plan, "rounds": res.rounds, "quality": res.quality,
                "coverage": res.coverage, "trace": res.trace, "latency_ms": res.latency_ms}, \
            (min(0.95, 0.4 + res.quality) if res.documents else 0.2), []


class HistoricalComparisonAgent(Agent):
    name, family = "historical_comparison", "knowledge"
    description = "Builds a structured then-vs-now comparison with the best historical match."

    async def execute(self, ctx: AgentContext):
        docs = [d for d in ctx.result("rag_retrieval").get("documents", []) if d.get("collection") == "historical_matches"]
        if not docs:
            return {"comparison": None, "reason": "no sufficiently similar historical match"}, 0.2, []
        best = docs[0]
        st = ctx.state
        patterns_now = {p["type"] for p in st.get("new_patterns", [])} | {p["type"] for p in ctx.runtime.patterns.active_list()}
        shared = sorted(patterns_now & set(best.get("patterns", [])))
        return {"comparison": {"doc_id": best["doc_id"], "title": best["title"], "source": best["source"],
                               "synthetic": best.get("synthetic", False), "shared_patterns": shared,
                               "shared_teams": [team_name(t) for t in set(best.get("teams", [])) & set(st.get("team_ids", []))],
                               "then": best["snippet"], "rerank_score": best["rerank_score"],
                               "why_selected": best.get("why_selected", [])}}, \
            min(0.9, 0.45 + best["rerank_score"]), []


class SimilarMatchAgent(Agent):
    name, family = "similar_match", "knowledge"
    description = "Finds similar moments earlier in this match (pattern history and stored insights)."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        types = {p["type"] for p in st.get("new_patterns", [])}
        minute = ctx.event.minute if ctx.event else 999
        earlier = [h for h in ctx.runtime.patterns.history
                   if h["event"] == "start" and h["minute"] < minute and (not types or h["type"] in types)]
        same_cat = [i for i in ctx.runtime.insights if i.category == st.get("category") and i.minute < minute][-3:]
        return {"earlier_patterns": [{"type": h["type"], "team": team_name(h["team_id"]), "minute": h["minute"],
                                      "summary": h["summary"]} for h in earlier[-3:]],
                "earlier_insights": [{"insight_id": i.insight_id, "minute": i.minute, "headline": i.headline} for i in same_cat]}, \
            0.7 if earlier or same_cat else 0.3, []
