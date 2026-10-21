import time

from app.agents.router import score_event
from app.graph.builder import new_run_id
from app.services.observability import OBS


def _state(rt, ev, **kw):
    eng = rt.engine
    sig, cat, reasons = score_event(ev, {}, [], ev.minute, eng.score["azc"] - eng.score["tha"])
    return {"run_id": new_run_id(), "mode": "event", "match_id": rt.match_id, "timestamp": time.time(), "event_obj": ev,
            "event_delta": {}, "pattern_changes": [], "new_patterns": [], "significance": sig, "category": cat,
            "reasons": reasons, "agent_results": {}, "graph_path": [], **kw}


async def test_routine_event_short_circuits(loaded):
    c, rt = loaded
    ev = next(e for e in rt.engine.events if e.type.value == "PASS")
    out = await c.event_graph.ainvoke(_state(rt, ev))
    assert out["graph_path"] == ["ingest_event", "classify_event", "update_context_only"]


async def test_goal_runs_full_graph_with_provenance(loaded):
    c, rt = loaded
    c.kv._d.clear()  # the live pipeline already analysed this goal; force a cold run
    goal = next(e for e in rt.engine.events if e.type.value == "GOAL")
    out = await c.event_graph.ainvoke(_state(rt, goal))
    path = out["graph_path"]
    for node in ("route_agents", "run_analysis", "retrieve_memory", "retrieve_context:4docs", "compare_history",
                 "generate_explanation:local-reasoner", "personalize", "generate_3d_command", "publish_insight"):
        assert any(p.startswith(node.split(":")[0]) for p in path), node
    ins = out["final_insight"]
    assert ins["provenance"]["source_events"] and goal.event_id in ins["provenance"]["source_events"]
    assert ins["provenance"]["retrieved_documents"]
    assert set(ins["explanations"]) == {"beginner", "intermediate", "advanced", "professional"}
    assert any(cmd["type"] == "camera" for cmd in ins["visualization"])
    assert ins["voice_scripts"]["kids"]


async def test_second_run_hits_shared_insight_cache(loaded):
    c, rt = loaded
    goal = next(e for e in rt.engine.events if e.type.value == "GOAL")
    await c.event_graph.ainvoke(_state(rt, goal))
    out = await c.event_graph.ainvoke(_state(rt, goal))
    assert "check_cache:hit" in out["graph_path"] and out["final_insight"]["provenance"]["cache_hit"]


async def test_pipeline_produced_pattern_insights(loaded):
    _, rt = loaded
    cats = {i.category for i in rt.insights}
    assert "GOAL" in cats and ("HIGH_PRESS" in cats or "TACTICAL_SHIFT" in cats)
    assert OBS.counters["events_fast_path_only"] > OBS.counters["events_analysed"] * 5  # most events cost nothing


async def test_query_graph_and_zero_token_restyle(loaded):
    c, rt = loaded
    a = await c.ask(rt.match_id, "Why did Thames Athletic score?", user_id="alex")
    assert a["statistics"]["intent"] == "WHY" and a["headline"]
    before = OBS.counters.get("restyles_zero_token", 0)
    b = await c.ask(rt.match_id, "Explain this like I'm a beginner", user_id="alex")
    assert "restyle_answer" in b["provenance"]["graph_path"]
    assert OBS.counters["restyles_zero_token"] == before + 1
    assert b["statistics"]["level"] == "beginner"


async def test_compare_question_uses_agentic_rag(loaded):
    c, rt = loaded
    a = await c.ask(rt.match_id, "Compare this with a historical match", user_id="sam")
    assert any(p.startswith("retrieve_context") for p in a["provenance"]["graph_path"])
    assert a["provenance"]["retrieved_documents"]


async def test_story(loaded):
    c, rt = loaded
    s = await c.story_service.build(rt)
    assert s["moments"] and s["facts"]["goals"] and s["facts"]["player_of_the_match"]
