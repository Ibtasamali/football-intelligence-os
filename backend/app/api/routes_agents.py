"""Agents: on-demand analysis, catalog, observability, graph topology."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.registry import catalog
from app.agents.router import score_event
from app.api.deps import container, runtime_or_404
from app.graph.builder import new_run_id
from app.data.teams import player_name, team_name
from app.services.observability import OBS
from app.services.tracing import trace_summary

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/analyze")
async def analyze(body: dict, c=Depends(container)):
    """Force a full LangGraph analysis of one event (defaults to the latest)."""
    match_id = body.get("match_id")
    rt = runtime_or_404(c, match_id)
    eng = rt.engine
    ev = eng.by_id.get(body.get("event_id")) if body.get("event_id") else (eng.events[-1] if eng.events else None)
    if not ev:
        raise HTTPException(404, "event not found")
    sig, cat, reasons = score_event(ev, {}, [], ev.minute, eng.score[eng.home] - eng.score[eng.away])
    state = {"run_id": new_run_id(), "mode": "event", "match_id": match_id, "timestamp": time.time(), "event_obj": ev,
             "event_delta": {}, "pattern_changes": [], "new_patterns": [], "significance": max(sig, 0.45),
             "category": cat if cat != "ROUTINE" else "TACTICAL_SHIFT", "reasons": reasons + ["on-demand analysis"],
             "agent_results": {}, "graph_path": []}
    out = await c.run_event_graph(state)
    return {"insight": out.get("final_insight"), "graph_path": out.get("graph_path"), "routing": out.get("routing")}


@router.get("/catalog")
async def agent_catalog():
    return {"agents": catalog()}


@router.get("/observability")
async def observability(c=Depends(container)):
    return {**OBS.summary(), "workers": c.pool.status(), "cag": {"hits": c.cag.hits, "misses": c.cag.misses,
                                                                  "backend": c.kv.backend},
            "llm_enabled": c.llm.enabled, "speech_enabled": c.speech.enabled}


@router.get("/traces")
async def traces(match_id: str | None = None, limit: int = Query(300, le=1000)):
    """Metadata-only OpenTelemetry spans for the local tracing dashboard."""
    return trace_summary(match_id, limit)


@router.post("/desk")
async def run_desk(body: dict, c=Depends(container)):
    """Run the Microsoft Agent Framework performance desk and publish a verified PDF report."""
    rt = runtime_or_404(c, body.get("match_id"))
    if not rt.engine.events:
        raise HTTPException(409, "Match has no events yet — start the match first")
    return await c.agent_desk.run(rt)


@router.get("/runs")
async def runs(match_id: str, limit: int = Query(30, le=200), c=Depends(container)):
    return {"runs": await c.db.find("agent_runs", {"match_id": match_id}, sort=[("created_at", -1)], limit=limit)}


@router.get("/graph")
async def graph(c=Depends(container)):
    return {"event_graph": c.event_graph.get_graph().draw_mermaid(), "query_graph": c.query_graph.get_graph().draw_mermaid()}


NODE_INFO = {
    "ingest_event": ("Ingest", "The raw event enters the graph: who, where, when."),
    "classify_event": ("Classify", "Cheap rules score how significant this moment is. Routine plays stop here at zero cost."),
    "check_cache": ("Shared cache", "If any viewer already triggered this insight, reuse it (zero tokens)."),
    "route_agents": ("Agent router", "Chooses which specialist agents run, in which parallel waves, and which model tier."),
    "run_analysis": ("Analysis agents", "Perception and tactical agents run in parallel waves; all deterministic, zero tokens."),
    "retrieve_memory": ("MAG memory", "Long-term football memory and fan history."),
    "retrieve_context": ("Agentic RAG", "Plans queries, retrieves, reranks, validates evidence and re-plans if it is weak."),
    "compare_history": ("History agents", "Builds a then-vs-now comparison and finds similar moments earlier in the match."),
    "predict_next_state": ("Prediction", "Probabilistic next-state predictions, always labelled as predictions."),
    "generate_explanation": ("Expert analyst (LLM)", "One Azure OpenAI call over the evidence package writes every knowledge level."),
    "verify_claims": ("Fact verification", "Every number, event and source is checked; failures loop back once with feedback."),
    "personalize": ("Experience agents", "Beginner text, broadcast line, story beats, fan perspective and alerts."),
    "generate_3d_command": ("3D visualisation", "Declarative scene commands: zones, players, lanes, camera."),
    "generate_voice": ("Voice narrator", "A spoken line for each persona."),
    "publish_insight": ("Publish", "Final assembly with confidence and full provenance."),
}


@router.post("/trace")
async def trace(body: dict, c=Depends(container)):
    """Replay one moment through the LangGraph and return every step with each agent's findings (walkthrough/video)."""
    from app.agents.registry import AGENTS
    from app.agents.summaries import summarize
    match_id = body.get("match_id")
    rt = runtime_or_404(c, match_id)
    eng = rt.engine
    ins = next((i for i in rt.insights if i.insight_id == body.get("insight_id")), None)
    if ins is None:
        goals = [i for i in rt.insights if i.category == "GOAL"]
        ins = goals[-1] if goals else (rt.insights[-1] if rt.insights else None)
    ev = eng.by_id.get(body.get("event_id") or (ins.event_id if ins else None)) or (eng.events[-1] if eng.events else None)
    if ev is None:
        raise HTTPException(409, "No events yet — start the match first")
    sig, cat, reasons = score_event(ev, {}, [], ev.minute, eng.score[eng.home] - eng.score[eng.away])
    state = {"run_id": new_run_id(), "mode": "event", "match_id": match_id, "timestamp": time.time(), "event_obj": ev,
             "event_delta": {}, "pattern_changes": [], "new_patterns": list(ins.patterns) if ins else [],
             "significance": max(sig, ins.significance if ins else 0.45), "category": ins.category if ins else cat,
             "reasons": reasons, "agent_results": {}, "graph_path": [], "trace": True}
    steps = []
    t0 = time.perf_counter()
    async for upd in c.event_graph.astream(state, stream_mode="updates"):
        for node, part in upd.items():
            if not isinstance(part, dict):
                continue
            base = node.split(":")[0]
            title, desc = NODE_INFO.get(base, (base, ""))
            agents = []
            for name, r in (part.get("agent_results") or {}).items():
                a = AGENTS.get(name)
                agents.append({"agent": name, "family": a.family if a else "", "role": a.description if a else "",
                               "uses_llm": a.uses_llm if a else False, "status": r.get("status"),
                               "latency_ms": round(r.get("latency_ms", 0), 1), "tokens": r.get("tokens", 0),
                               "model": r.get("model"), "confidence": r.get("confidence"),
                               "findings": [x for x in summarize(name, {**(r.get("output") or {}), "_model": r.get("model")}) if x]})
            decision = []
            if base == "classify_event":
                decision = [f"Significance {state['significance']:.2f} → category {state['category']}"] + list(reasons)
            if base == "route_agents" and part.get("routing"):
                rp = part["routing"]
                decision = rp.get("reasons", []) + [f"Wave {i + 1}: {', '.join(w)}" for i, w in enumerate(rp.get("waves", []))] + \
                           ([f"Skipped (not needed): {', '.join(rp.get('skipped', []))}"] if rp.get("skipped") else [])
            if base == "check_cache":
                decision = ["Cache bypassed for this walkthrough (live runs reuse it)"]
            steps.append({"node": node, "title": title, "description": desc, "agents": agents, "decision": decision})
    ran = sorted({a["agent"] for s_ in steps for a in s_["agents"]})
    return {"event": {"clock": ev.clock, "type": ev.type.value, "player": player_name(ev.player_id) if ev.player_id else None,
                      "team": team_name(ev.team_id) if ev.team_id else None},
            "insight": {"headline": ins.headline, "category": ins.category} if ins else None,
            "steps": steps, "agents_ran": ran, "duration_ms": round((time.perf_counter() - t0) * 1000),
            "agents_all": [{"agent": n, "family": a.family, "role": a.description, "ran": n in ran} for n, a in AGENTS.items()]}
