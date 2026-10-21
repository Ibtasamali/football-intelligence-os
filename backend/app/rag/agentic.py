"""Agentic RAG: plan → multi-source retrieve → rerank → validate evidence → (re-plan) → synthesise.

The retriever first decides *whether* retrieval is needed at all. When it is, it builds per-collection
queries with entity filters, scores results with more than vector similarity, checks the evidence covers
what was asked, and broadens the search once if it does not. It never blindly forwards top-K.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field

from app.data.teams import player_name, team_name
from app.services.observability import OBS

PATTERN_QUERY = {
    "HIGH_PRESS": "high press PPDA turnovers pressing build-up",
    "FLANK_OVERLOAD": "flank overload overlapping full-back crosses wide channel",
    "DEEP_BLOCK": "deep low block defensive line protect lead",
    "TRANSITION_VULNERABILITY": "counter-attack transition rest defence full-backs high space behind",
    "MIDFIELD_SUPERIORITY": "numerical superiority midfield central overload field tilt",
    "SUBSTITUTION_IMPACT": "substitution impact tactical change game state",
}


@dataclass
class RetrievalRequest:
    reason: str                         # "pattern_start" | "goal" | "question" | ...
    teams: list[str] = field(default_factory=list)
    players: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    question: str | None = None
    intent: str | None = None
    cached_context_sufficient: bool = False


@dataclass
class QueryPlan:
    collection: str
    text: str
    k: int
    filters: dict | None = None


@dataclass
class RetrievalPlan:
    needed: bool
    rationale: str
    queries: list[QueryPlan] = field(default_factory=list)
    min_score: float = 0.12
    max_docs: int = 4


@dataclass
class RetrievalResult:
    documents: list[dict]
    plan: dict
    rounds: int
    quality: float
    coverage: dict
    latency_ms: float
    trace: list[str]


class AgenticRetriever:
    def __init__(self, vector_store) -> None:
        self.vs = vector_store

    # ---------------------------------------------------------------- planning
    def plan(self, req: RetrievalRequest) -> RetrievalPlan:
        historical_intents = {"COMPARE", "SIMILAR", "HISTORY"}
        if req.cached_context_sufficient and req.intent not in historical_intents and not req.patterns:
            return RetrievalPlan(False, "Live match context (CAG) answers this; no retrieval needed.")
        if req.reason in ("routine",):
            return RetrievalPlan(False, "Routine event; retrieval would add cost without new evidence.")

        topic = " ".join(PATTERN_QUERY.get(p, p.lower().replace("_", " ")) for p in req.patterns)
        names = " ".join(team_name(t) for t in req.teams) + " " + " ".join(player_name(p) for p in req.players)
        base = f"{req.question or ''} {topic} {names}".strip()
        queries = []
        if req.intent in historical_intents or req.reason in ("pattern_start", "goal", "question"):
            queries.append(QueryPlan("historical_matches", base, 6, {"teams": {"$in": req.teams}} if req.teams else None))
        if req.patterns or req.intent in ("WHY", "EXPLAIN", "EXPLAIN_SIMPLER", "EXPLAIN_EXPERT", "TACTICS"):
            queries.append(QueryPlan("knowledge_documents", f"{topic} {req.question or ''}".strip() or base, 3))
        if not queries:
            return RetrievalPlan(False, "No historical or conceptual evidence required for this request.")
        rationale = (f"Retrieve because {req.reason}"
                     + (f" with patterns {', '.join(req.patterns)}" if req.patterns else "")
                     + (f" (intent {req.intent})" if req.intent else "")
                     + f"; collections: {', '.join(q.collection for q in queries)}.")
        return RetrievalPlan(True, rationale, queries)

    # ---------------------------------------------------------------- scoring
    @staticmethod
    def _rerank(doc: dict, req: RetrievalRequest) -> tuple[float, list[str]]:
        why = []
        vec = float(doc.get("score", 0))
        teams = set(doc.get("teams", []))
        ent = len(teams & set(req.teams)) / max(1, len(set(req.teams))) if req.teams else 0
        players = len(set(doc.get("players", [])) & set(req.players)) / max(1, len(req.players)) if req.players else 0
        pat = len(set(doc.get("patterns", [])) & set(req.patterns)) / max(1, len(req.patterns)) if req.patterns else 0
        if ent:
            why.append(f"same teams ({', '.join(team_name(t) for t in teams & set(req.teams))})")
        if pat:
            why.append(f"same pattern ({', '.join(set(doc.get('patterns', [])) & set(req.patterns))})")
        if players:
            why.append("shared players")
        score = 0.48 * vec + 0.12 * ent + 0.25 * pat + 0.15 * players
        if doc.get("collection") == "knowledge_documents" and pat:
            score += 0.05
        return round(score, 4), why

    def _validate(self, docs: list[dict], req: RetrievalRequest, plan: RetrievalPlan) -> tuple[float, dict]:
        top = docs[: plan.max_docs]
        quality = round(sum(d["rerank_score"] for d in top) / len(top), 3) if top else 0.0
        coverage = {p: any(p in d.get("patterns", []) for d in top) for p in req.patterns}
        coverage["teams"] = any(set(d.get("teams", [])) & set(req.teams) for d in top) if req.teams else True
        return quality, coverage

    # ---------------------------------------------------------------- run
    async def retrieve(self, req: RetrievalRequest, plan: RetrievalPlan | None = None) -> RetrievalResult:
        t0 = time.perf_counter()
        plan = plan or self.plan(req)
        trace = [f"plan: {plan.rationale}"]
        if not plan.needed:
            return RetrievalResult([], asdict(plan), 0, 0.0, {}, 0.0, trace)
        OBS.incr("rag_retrievals")
        docs: list[dict] = []
        rounds = 0
        quality, coverage = 0.0, {}
        queries = plan.queries
        while rounds < 2:
            rounds += 1
            batches = await asyncio.gather(*(self.vs.search(q.collection, q.text, q.k, q.filters) for q in queries))
            seen = {d["doc_id"] for d in docs}
            for q, batch in zip(queries, batches):
                trace.append(f"round {rounds}: {q.collection} k={q.k} filters={q.filters} → {len(batch)} hits")
                for d in batch:
                    if d["doc_id"] in seen:
                        continue
                    seen.add(d["doc_id"])
                    d["rerank_score"], d["why_selected"] = self._rerank(d, req)
                    docs.append(d)
            docs = sorted((d for d in docs if d["rerank_score"] >= plan.min_score), key=lambda d: -d["rerank_score"])
            quality, coverage = self._validate(docs, req, plan)
            missing = [k for k, v in coverage.items() if not v]
            trace.append(f"validate: quality={quality} missing={missing or 'none'}")
            if quality >= 0.3 and not missing:
                break
            if rounds >= 2:
                trace.append("evidence still partial after re-plan; returning what is supported")
                break
            OBS.incr("rag_replans")
            queries = [QueryPlan(q.collection, q.text + " " + " ".join(PATTERN_QUERY.get(m, "") for m in missing),
                                 q.k + 4, None) for q in queries]
            trace.append("re-plan: broadened queries, dropped entity filters")
        final = []
        for d in docs[: plan.max_docs]:
            final.append({"doc_id": d["doc_id"], "title": d.get("title"), "collection": d.get("collection"),
                          "source": d.get("source"), "synthetic": d.get("synthetic", False),
                          "patterns": d.get("patterns", []), "teams": d.get("teams", []),
                          "score": d.get("score"), "rerank_score": d["rerank_score"],
                          "why_selected": d["why_selected"], "snippet": d.get("text", "")[:600]})
        return RetrievalResult(final, asdict(plan), rounds, quality, coverage,
                               round((time.perf_counter() - t0) * 1000, 1), trace)
