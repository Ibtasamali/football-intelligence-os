"""LangGraph orchestration.

Two compiled graphs share node implementations:

EVENT GRAPH
  ingest_event → classify_event ─(routine)→ update_context_only → END
                               └→ check_cache ─(hit)→ publish_insight → END
                                              └→ route_agents → run_analysis
  run_analysis ─(memory?)→ retrieve_memory ─(retrieval?)→ retrieve_context ─(docs?)→ compare_history
           └──────(retrieval?)──────────────┘                └───(none)──────────┐
  … → predict_next_state → generate_explanation → verify_claims ─(fail, retry)→ generate_explanation
                                                               └→ personalize → generate_3d_command
                                                                  → generate_voice → publish_insight → END
QUERY GRAPH
  ingest_query ─(restyle)→ restyle_answer → generate_voice → publish_answer
              ─(story)──→ match_story → generate_voice → publish_answer
              └→ check_cache ─(hit)→ publish_answer
                             └→ route_query → run_analysis → … (same knowledge/reasoning nodes) … → publish_answer
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import time

from langgraph.graph import END, StateGraph

from app.services.tracing import span
from app.agents.base import AgentContext
from app.agents.evidence import build_evidence, core_claims, verify_output
from app.agents.reasoning_agents import local_narrative
from app.agents.registry import AGENTS
from app.agents.router import plan_event, plan_query, score_event
from app.cag.context import ContextCache
from app.data.teams import player_name, team_name
from app.graph.state import FootballState
from app.models.domain import Claim, Insight, Prediction, Provenance, new_id
from app.services.observability import OBS
from app.voice.intent import detect_intent
from app.voice.personas import LEVEL_FOR_PERSONA

LEVELS = ["beginner", "intermediate", "advanced", "professional"]
NO_EVIDENCE = "I don't have enough evidence to make a reliable conclusion."


def traced(name: str, fn):
    """One OpenTelemetry span per LangGraph node, so the trace waterfall shows the real graph path."""
    if not asyncio.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def node(state):
        with span(f"node {name}", run_id=state.get("run_id"), match_id=state.get("match_id")):
            return await fn(state)
    return node


def build_graphs(c):
    """`c` is the service Container. Returns (event_graph, query_graph)."""

    def rt(state):
        return c.runtimes[state["match_id"]]

    def actx(state, **extras):
        return AgentContext(runtime=rt(state), services=c, state=state, event=state.get("event_obj"), extras=extras)

    async def run_agents(state, names: list[str]) -> dict:
        ctx = actx(state)
        results = await asyncio.gather(*(AGENTS[n].run(ctx) for n in names if n in AGENTS))
        return {r.agent: r.model_dump() for r in results}

    async def run_one(state, name: str) -> dict:
        r = await AGENTS[name].run(actx(state))
        return r.model_dump()

    # ================================================================ event nodes
    async def ingest_event(state: FootballState):
        ev = state["event_obj"]
        tid = ev.team_id
        players = [p for p in (ev.player_id, ev.related_player_id) if p]
        for p in state.get("new_patterns", []):
            players += p.get("players", [])
        opp = rt(state).engine.other(tid) if tid else None
        return {"team_id": tid, "team": team_name(tid) if tid else None, "opponent": opp,
                "team_ids": [t for t in (tid, opp) if t],
                "player_ids": list(dict.fromkeys(players)), "player": player_name(ev.player_id) if ev.player_id else None,
                "event": {"event_id": ev.event_id, "type": ev.type.value, "clock": ev.clock},
                "event_summary": f"{ev.type.value} {team_name(tid) if tid else ''} {player_name(ev.player_id) if ev.player_id else ''}",
                "score": dict(rt(state).engine.score), "graph_path": ["ingest_event"]}

    async def classify_event(state: FootballState):
        if state.get("significance") is not None and state.get("category"):
            return {"graph_path": ["classify_event"]}
        eng = rt(state).engine
        ev = state["event_obj"]
        changes = state.get("pattern_changes", [])
        sig, cat, reasons = score_event(ev, state.get("event_delta", {}), changes, ev.minute,
                                        eng.score[eng.home] - eng.score[eng.away])
        return {"significance": sig, "category": cat, "reasons": reasons, "tactical_significance": sig,
                "graph_path": ["classify_event"]}

    def after_classify(state) -> str:
        return "routine" if state["significance"] < c.settings.significance_threshold else "analyse"

    async def update_context_only(state: FootballState):
        return {"graph_path": ["update_context_only"]}

    async def check_cache(state: FootballState):
        ev = state["event_obj"]
        key = "insight:" + hashlib.sha1(f"{state['match_id']}|{ev.event_id}|{ev.type.value}".encode()).hexdigest()[:24]
        hit = None if state.get("trace") else await c.json_kv.get_json(key)
        if hit:
            OBS.incr("insight_cache_hits")
            hit["provenance"]["cache_hit"] = True
            return {"cache_key": key, "cache_hit": True, "final_insight": hit, "graph_path": ["check_cache:hit"]}
        return {"cache_key": key, "cache_hit": False, "graph_path": ["check_cache:miss"]}

    def after_cache(state) -> str:
        return "hit" if state.get("cache_hit") else "miss"

    async def route_agents(state: FootballState):
        plan = plan_event(state["event_obj"], state["significance"], state["category"], state.get("new_patterns", []),
                          c.settings.large_model_threshold)
        await c.broadcast(state["match_id"], {"type": "routing", "run_id": state["run_id"], "plan": plan.to_dict(),
                                              "event_id": state["event_obj"].event_id})
        return {"routing": plan.to_dict(), "model_tier": plan.model_tier, "retrieval_reason": plan.retrieval_reason,
                "graph_path": ["route_agents"]}

    async def run_analysis(state: FootballState):
        results: dict = {}
        working = dict(state)
        for wave in state["routing"]["waves"]:
            out = await run_agents({**working, "agent_results": {**state.get("agent_results", {}), **results}}, wave)
            results.update(out)
        mom = results.get("momentum", {}).get("output", {})
        cag = results.get("cag_context", {}).get("output", {})
        return {"agent_results": results, "momentum": mom, "cached_context": cag,
                "confidence_scores": {k: v["confidence"] for k, v in results.items()},
                "formation": results.get("formation", {}).get("output", {}),
                "tactical_context": results.get("tactical_analysis", {}).get("output", {}),
                "graph_path": ["run_analysis"]}

    def after_analysis(state) -> str:
        r = state["routing"]
        if r["needs_memory"]:
            return "memory"
        if r["needs_retrieval"]:
            return "retrieve"
        return "predict"

    async def retrieve_memory(state: FootballState):
        r = await run_one(state, "mag_memory")
        return {"agent_results": {"mag_memory": r}, "memories": r["output"].get("memories", []),
                "graph_path": ["retrieve_memory"]}

    def after_memory(state) -> str:
        return "retrieve" if state["routing"]["needs_retrieval"] else "predict"

    async def retrieve_context(state: FootballState):
        r = await run_one(state, "rag_retrieval")
        return {"agent_results": {"rag_retrieval": r}, "retrieved_documents": r["output"].get("documents", []),
                "graph_path": [f"retrieve_context:{len(r['output'].get('documents', []))}docs"]}

    def after_retrieval(state) -> str:
        return "compare" if state.get("retrieved_documents") else "predict"

    async def compare_history(state: FootballState):
        out = await run_agents(state, ["historical_comparison", "similar_match"])
        return {"agent_results": out, "graph_path": ["compare_history"]}

    async def predict_next_state(state: FootballState):
        if state.get("mode") == "query" and state.get("intent") not in ("PREDICT", "WHY", "TACTICS", "GENERAL", "WHAT_HAPPENED"):
            return {"graph_path": ["predict_next_state:skipped"]}
        r = await run_one(state, "prediction")
        return {"agent_results": {"prediction": r}, "predictions": r["output"].get("predictions", []),
                "graph_path": ["predict_next_state"]}

    async def generate_explanation(state: FootballState):
        r = await run_one(state, "expert_analyst")
        first = {} if state.get("first_draft") else {"first_draft": {k: r["output"].get(k) for k in
                                                                     ("headline", "explanations", "commentary", "claims", "_model")}}
        return {**first, "agent_results": {"expert_analyst": r}, "narrative": r["output"],
                "verification_attempts": state.get("verification_attempts", 0) + 1,
                "graph_path": [f"generate_explanation:{r['model']}"]}

    async def verify_claims(state: FootballState):
        r = await run_one(state, "fact_verification")
        rep = r["output"]
        return {"agent_results": {"fact_verification": r}, "verification": rep,
                "verification_feedback": rep.get("issues", []),
                "graph_path": [f"verify_claims:{'pass' if rep.get('passed') else 'fail'}"]}

    def after_verify(state) -> str:
        rep = state.get("verification", {})
        if rep.get("passed"):
            return "ok"
        narrative = state.get("narrative", {})
        if not state.get("verification_feedback"):
            return "ok"
        if state.get("verification_attempts", 0) < 2 and not narrative.get("fallback"):
            OBS.incr("verification_retries")
            return "retry"
        return "ok"

    async def personalize(state: FootballState):
        names = ["casual_fan_explanation", "broadcast_commentary", "storytelling", "fan_personalization", "alert"]
        out = await run_agents(state, names)
        return {"agent_results": out, "graph_path": ["personalize"]}

    async def generate_3d_command(state: FootballState):
        r = await run_one(state, "visualization_3d")
        return {"agent_results": {"visualization_3d": r}, "visualization_command": r["output"].get("commands", []),
                "graph_path": ["generate_3d_command"]}

    async def generate_voice(state: FootballState):
        r = await run_one(state, "voice_narrator")
        scripts = r["output"].get("voice_scripts", {})
        return {"agent_results": {"voice_narrator": r}, "voice_script": scripts.get(state.get("persona") or "casual_commentator", ""),
                "graph_path": ["generate_voice"]}

    def assemble(state: FootballState, *, category: str, answer: bool) -> Insight:
        res = state.get("agent_results", {})
        narrative = dict(state.get("narrative") or {})
        evidence = narrative.pop("_evidence", None) or build_evidence(state, rt(state))
        rep = state.get("verification", {}) or {}
        explanations = {k: (narrative.get("explanations") or {}).get(k, "") for k in LEVELS}
        casual = res.get("casual_fan_explanation", {}).get("output", {}).get("beginner")
        if casual:
            explanations["beginner"] = casual
        commentary = res.get("broadcast_commentary", {}).get("output", {}).get("commentary") or narrative.get("commentary", "")
        headline = narrative.get("headline", "")
        historical_note = narrative.get("historical_note", "")
        confidence = res.get("final_answer", {}).get("output", {}).get("overall_confidence", 0.6)
        if not rep.get("passed", True):
            # Second failure: replace every field with issues by its grounded template counterpart.
            safe = local_narrative(evidence, state)
            bad_fields = {i.split(":")[0] for i in rep.get("issues", [])}
            for lvl in LEVELS:
                if lvl in bad_fields:
                    explanations[lvl] = safe["explanations"][lvl]
            if "headline" in bad_fields:
                headline = safe["headline"]
            if "commentary" in bad_fields:
                commentary = safe["commentary"]
            if "historical_note" in bad_fields:
                historical_note = safe["historical_note"]
            confidence = round(confidence - 0.15, 3)
            OBS.incr("claims_replaced_after_verification")
        if answer and confidence < 0.45:
            headline = NO_EVIDENCE
            explanations = {k: NO_EVIDENCE for k in LEVELS}
        claims = [Claim(**{k: v for k, v in cl.items() if k in ("text", "event_ids", "metric_refs", "verified", "reason")})
                  for cl in rep.get("verified_claims", [])]
        if len(claims) < 3:  # top up with deterministic facts, verified the same way
            have = {c.text for c in claims}
            core = verify_output({"claims": [c for c in core_claims(evidence) if c["text"] not in have]}, evidence, rt(state).engine)
            claims += [Claim(**{k: v for k, v in cl.items() if k in ("text", "event_ids", "metric_refs", "verified", "reason")})
                       for cl in core["verified_claims"]][: 3 - len(claims)]
        ev = state.get("event_obj")
        story = res.get("storytelling", {}).get("output", {})
        stats = {"metrics": {k: v for k, v in list(evidence.get("metrics", {}).items())[:40]},
                 "story": story, "alert": res.get("alert", {}).get("output", {}),
                 "routing": state.get("routing"), "comparison": res.get("historical_comparison", {}).get("output", {}).get("comparison"),
                 "rag_trace": res.get("rag_retrieval", {}).get("output", {}).get("trace"),
                 "verification_issues": rep.get("issues", [])}
        model = narrative.get("_model") or res.get("expert_analyst", {}).get("model", "none")
        if getattr(c, "eval_mode", False):
            stats["first_draft"] = state.get("first_draft")
            stats["evidence"] = evidence
        eng = rt(state).engine
        last = ev or (eng.events[-1] if eng.events else None)
        return Insight(
            match_id=state["match_id"], event_id=ev.event_id if ev else None,
            minute=last.minute if last else 0, second=last.second if last else 0,
            category=category, headline=headline or "Insight", explanations=explanations, commentary=commentary,
            perspectives=res.get("fan_personalization", {}).get("output", {}).get("perspectives", {}),
            voice_scripts=res.get("voice_narrator", {}).get("output", {}).get("voice_scripts", {}),
            historical_note=historical_note, significance=state.get("significance", 0.5),
            team_id=state.get("team_id"), player_ids=state.get("player_ids", [])[:6], claims=claims,
            predictions=[Prediction(**p) for p in state.get("predictions", [])],
            patterns=state.get("new_patterns", []), statistics=stats,
            visualization=state.get("visualization_command", []),
            verification={"passed": rep.get("passed"), "claim_support": rep.get("claim_support"),
                          "issues": rep.get("issues", []), "unverified_claims": rep.get("unverified_claims", []),
                          "attempts": state.get("verification_attempts", 0)},
            provenance=Provenance(
                source_events=evidence.get("valid_event_ids", [])[:30],
                retrieved_documents=[{k: d.get(k) for k in ("doc_id", "title", "source", "synthetic", "rerank_score", "why_selected")}
                                     for d in state.get("retrieved_documents", [])],
                memories=[{k: m.get(k) for k in ("memory_id", "text", "source", "score")} for m in state.get("memories", [])],
                model=model, agents_used=[k for k, v in res.items() if v.get("status") in ("complete", "cached")],
                confidence=confidence, graph_path=state.get("graph_path", [])))

    async def publish_insight(state: FootballState):
        runtime = rt(state)
        if state.get("trace"):  # walkthrough run: assemble but never publish a duplicate card
            fa = await run_one(state, "final_answer")
            st2 = {**state, "agent_results": {**state.get("agent_results", {}), "final_answer": fa}}
            insight = assemble(st2, category=state["category"], answer=False)
            return {"final_insight": insight.model_dump(), "agent_results": {"final_answer": fa}, "graph_path": ["publish_insight"]}
        if state.get("cache_hit"):
            insight = Insight(**state["final_insight"])
        else:
            fa = await run_one(state, "final_answer")
            st2 = {**state, "agent_results": {**state.get("agent_results", {}), "final_answer": fa}}
            insight = assemble(st2, category=state["category"], answer=False)
            insight.provenance.graph_path = state.get("graph_path", []) + ["publish_insight"]
            await c.json_kv.set_json(state["cache_key"], insight.model_dump(), c.settings.insight_cache_ttl_seconds)
        await c.publish_insight(runtime, insight)
        if not state.get("cache_hit") and (state.get("new_patterns") or state["category"] == "GOAL"):
            ev = state["event_obj"]
            await c.memory.remember(kind="match_moment", text=f"{ev.clock} {insight.headline}. {insight.explanations.get('intermediate', '')}",
                                    entities=state.get("team_ids", []) + state.get("player_ids", [])[:3],
                                    source=f"Live analysis, match {state['match_id']}", importance=0.6,
                                    match_id=state["match_id"], extra={"minute": ev.minute, "insight_id": insight.insight_id,
                                                                        "patterns": [p["type"] for p in state.get("new_patterns", [])]})
        return {"final_insight": insight.model_dump(), "graph_path": ["publish_insight"]}

    # ================================================================ query nodes
    async def ingest_query(state: FootballState):
        intent = detect_intent(state["question"], [rt(state).engine.home, rt(state).engine.away])
        profile = state.get("profile") or {}
        persona = state.get("persona") or profile.get("persona") or "casual_commentator"
        level = intent.style_override or state.get("level") or profile.get("knowledge_level") or LEVEL_FOR_PERSONA.get(persona, "intermediate")
        runtime = rt(state)
        ctx = await c.cag.get(state["match_id"])
        teams = intent.teams or [runtime.engine.home, runtime.engine.away]
        players = intent.players
        latest = runtime.find_focus(state["question"], intent.teams, state.get("user_id"))
        if latest and not players:
            players = latest.player_ids[:3]
        return {"intent": intent.name, "level": level, "persona": persona, "team_ids": teams, "player_ids": players,
                "team_id": latest.team_id if latest else None, "cached_context": ctx or {},
                "cached_context_sufficient": ContextCache.sufficient_for(intent.name, ctx),
                "category": "ANSWER", "significance": 0.5, "event_obj": None,
                "focus_insight_id": latest.insight_id if latest else None,
                "graph_path": [f"ingest_query:{intent.name}"]}

    def after_ingest_query(state) -> str:
        runtime = rt(state)
        if state["intent"] in ("EXPLAIN_SIMPLER", "EXPLAIN_EXPERT") and runtime.last_focus_for(state.get("user_id")):
            return "restyle"
        if state["intent"] == "STORY":
            return "story"
        return "cache"

    async def restyle_answer(state: FootballState):
        """Same facts, different audience: reuse the already-verified multi-level explanations (0 tokens)."""
        runtime = rt(state)
        prev = runtime.last_focus_for(state.get("user_id"))
        OBS.incr("restyles_zero_token")
        level = state["level"]
        text = prev.explanations.get(level) or prev.explanations.get("intermediate", "")
        ins = prev.model_copy(deep=True)
        ins.insight_id = new_id("ans")
        ins.category = "ANSWER"
        ins.headline = f"{'Simply put' if level == 'beginner' else 'Analyst view'}: {prev.headline}"
        ins.provenance.graph_path = state.get("graph_path", []) + ["restyle_answer"]
        ins.provenance.cache_hit = True
        ins.statistics = {**ins.statistics, "restyled_from": prev.insight_id, "level": level, "answer": text}
        return {"final_insight": ins.model_dump(), "narrative": {"explanations": ins.explanations, "commentary": text},
                "agent_results": {"expert_analyst": {"output": {"explanations": ins.explanations, "commentary": text}, "status": "cached",
                                                     "confidence": ins.provenance.confidence, "model": "reuse"}},
                "graph_path": ["restyle_answer"]}

    async def match_story(state: FootballState):
        story = await c.story_service.build(rt(state), tier="large")
        text = story["how_won"]
        return {"final_insight": None, "narrative": {"story": story, "headline": story["headline"],
                                                     "explanations": {k: text for k in LEVELS}, "commentary": story["headline"]},
                "agent_results": {"expert_analyst": {"output": {"explanations": {k: text for k in LEVELS},
                                                                "commentary": story["headline"]}, "status": "complete",
                                                     "confidence": 0.8, "model": story.get("model", "")}},
                "graph_path": ["match_story"]}

    async def check_query_cache(state: FootballState):
        ctx = state.get("cached_context") or {}
        version_bucket = (ctx.get("version", 0) // 15)  # answers stay valid for ~15 context versions
        norm = " ".join(state["question"].lower().split())
        key = "answer:" + hashlib.sha1(f"{state['match_id']}|{rt(state).session}|{version_bucket}|{state['intent']}|{norm}".encode()).hexdigest()[:24]
        hit = await c.json_kv.get_json(key)
        if hit:
            OBS.incr("answer_cache_hits")
            hit["provenance"]["cache_hit"] = True
            return {"cache_key": key, "cache_hit": True, "final_insight": hit, "graph_path": ["check_cache:hit"]}
        return {"cache_key": key, "cache_hit": False, "graph_path": ["check_cache:miss"]}

    async def route_query(state: FootballState):
        plan = plan_query(state["intent"], state.get("cached_context_sufficient", False))
        return {"routing": plan.to_dict(), "model_tier": plan.model_tier, "retrieval_reason": plan.retrieval_reason,
                "graph_path": ["route_query"]}

    async def publish_answer(state: FootballState):
        runtime = rt(state)
        if state.get("final_insight"):
            insight = Insight(**state["final_insight"])
            if state.get("agent_results", {}).get("voice_narrator"):
                insight.voice_scripts = state["agent_results"]["voice_narrator"]["output"].get("voice_scripts", insight.voice_scripts)
        else:
            fa = await run_one(state, "final_answer")
            st2 = {**state, "agent_results": {**state.get("agent_results", {}), "final_answer": fa}}
            insight = assemble(st2, category="ANSWER", answer=True)
            insight.statistics["question"] = state["question"]
            insight.statistics["intent"] = state["intent"]
            if state.get("narrative", {}).get("story"):
                insight.statistics["story"] = state["narrative"]["story"]
            await c.json_kv.set_json(state["cache_key"], insight.model_dump(), 600) if state.get("cache_key") else None
        insight.statistics["level"] = state["level"]
        insight.statistics["answer"] = insight.explanations.get(state["level"]) or insight.explanations.get("intermediate", "")
        insight.provenance.graph_path = state.get("graph_path", []) + ["publish_answer"]
        runtime.remember_answer(state.get("user_id"), insight)
        if state.get("user_id"):
            await c.memory.remember_conversation(state["user_id"], state.get("tenant_id", "demo"), state["question"],
                                                 insight.headline, state.get("team_ids", []), state["match_id"])
        await c.db.upsert("insights", {"insight_id": insight.insight_id}, insight.model_dump())
        return {"final_insight": insight.model_dump(), "graph_path": ["publish_answer"]}

    # ================================================================ wiring
    shared = {
        "run_analysis": run_analysis, "retrieve_memory": retrieve_memory, "retrieve_context": retrieve_context,
        "compare_history": compare_history, "predict_next_state": predict_next_state,
        "generate_explanation": generate_explanation, "verify_claims": verify_claims, "personalize": personalize,
        "generate_3d_command": generate_3d_command, "generate_voice": generate_voice,
    }

    def wire_reasoning(g: StateGraph, terminal: str):
        g.add_conditional_edges("run_analysis", after_analysis,
                                {"memory": "retrieve_memory", "retrieve": "retrieve_context", "predict": "predict_next_state"})
        g.add_conditional_edges("retrieve_memory", after_memory, {"retrieve": "retrieve_context", "predict": "predict_next_state"})
        g.add_conditional_edges("retrieve_context", after_retrieval, {"compare": "compare_history", "predict": "predict_next_state"})
        g.add_edge("compare_history", "predict_next_state")
        g.add_edge("predict_next_state", "generate_explanation")
        g.add_edge("generate_explanation", "verify_claims")
        g.add_conditional_edges("verify_claims", after_verify, {"retry": "generate_explanation", "ok": "personalize"})
        g.add_edge("personalize", "generate_3d_command")
        g.add_edge("generate_3d_command", "generate_voice")
        g.add_edge("generate_voice", terminal)

    eg = StateGraph(FootballState)
    for name, fn in {"ingest_event": ingest_event, "classify_event": classify_event, "update_context_only": update_context_only,
                     "check_cache": check_cache, "route_agents": route_agents, "publish_insight": publish_insight, **shared}.items():
        eg.add_node(name, traced(name, fn))
    eg.set_entry_point("ingest_event")
    eg.add_edge("ingest_event", "classify_event")
    eg.add_conditional_edges("classify_event", after_classify, {"routine": "update_context_only", "analyse": "check_cache"})
    eg.add_edge("update_context_only", END)
    eg.add_conditional_edges("check_cache", after_cache, {"hit": "publish_insight", "miss": "route_agents"})
    eg.add_edge("route_agents", "run_analysis")
    wire_reasoning(eg, "publish_insight")
    eg.add_edge("publish_insight", END)

    qg = StateGraph(FootballState)
    for name, fn in {"ingest_query": ingest_query, "restyle_answer": restyle_answer, "match_story": match_story,
                     "check_cache": check_query_cache, "route_query": route_query, "publish_answer": publish_answer,
                     **shared}.items():
        qg.add_node(name, traced(name, fn))
    qg.set_entry_point("ingest_query")
    qg.add_conditional_edges("ingest_query", after_ingest_query,
                             {"restyle": "restyle_answer", "story": "match_story", "cache": "check_cache"})
    qg.add_edge("restyle_answer", "generate_voice")
    qg.add_edge("match_story", "generate_voice")
    qg.add_conditional_edges("check_cache", after_cache, {"hit": "publish_answer", "miss": "route_query"})
    qg.add_edge("route_query", "run_analysis")
    wire_reasoning(qg, "publish_answer")
    qg.add_edge("publish_answer", END)

    return eg.compile(), qg.compile()


def new_run_id() -> str:
    return new_id("run") + f"_{int(time.time())}"
