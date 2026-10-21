from app.agents.registry import AGENTS
from app.agents.router import plan_event, plan_query, score_event
from app.models.domain import EventType, MatchEvent


def ev(t, **kw):
    return MatchEvent(match_id="m", seq=1, minute=kw.pop("minute", 30), type=t, team_id="azc", player_id="azc_9", **kw)


def test_thirty_agents_registered():
    assert len(AGENTS) == 30


def test_routine_pass_needs_no_llm():
    sig, cat, _ = score_event(ev(EventType.PASS, outcome="success"), {}, [], 30, 0)
    assert sig < 0.25 and cat == "ROUTINE"


def test_goal_is_max_significance_and_large_model():
    sig, cat, _ = score_event(ev(EventType.GOAL), {}, [], 30, 0)
    assert sig == 1.0 and cat == "GOAL"
    plan = plan_event(ev(EventType.GOAL), sig, cat, [], 0.7)
    assert plan.model_tier == "large" and plan.needs_retrieval and plan.needs_memory
    assert "goal_probability" in plan.waves[1]


def test_shot_significance_scales_with_xg():
    lo, _, _ = score_event(ev(EventType.SHOT, meta={"xg": 0.03}), {}, [], 30, 0)
    hi, _, _ = score_event(ev(EventType.SHOT, meta={"xg": 0.45}), {}, [], 30, 0)
    assert hi > lo


def test_pattern_start_routes_pattern_specialists():
    class P:
        type = "HIGH_PRESS"
    sig, cat, _ = score_event(ev(EventType.PRESSURE), {}, [("start", P())], 30, 0)
    assert sig >= 0.7 and cat == "HIGH_PRESS"
    plan = plan_event(ev(EventType.PRESSURE), sig, cat, [{"type": "HIGH_PRESS"}], 0.7)
    assert "pressing_analysis" in plan.waves[1] and plan.needs_retrieval
    assert plan.skipped  # agents not needed are not run


def test_query_routing_uses_cag_before_rag():
    assert not plan_query("STATS", cag_sufficient=True).needs_retrieval
    assert plan_query("COMPARE", cag_sufficient=True).needs_retrieval
    assert plan_query("WHY", cag_sufficient=False).needs_retrieval


async def test_fan_perspective_follows_pattern_team(loaded):
    """A Thames pattern triggered by an Azure City event must still be 'good for Thames'."""
    from app.agents.base import AgentContext
    from app.agents.experience_agents import FanPersonalizationAgent
    c, rt = loaded
    st = {"team_id": "azc", "category": "TACTICAL_SHIFT",
          "new_patterns": [{"type": "FLANK_OVERLOAD", "team_id": "tha"}]}
    out, _, _ = await FanPersonalizationAgent().execute(AgentContext(runtime=rt, services=c, state=st))
    assert "Good sign for Thames" in out["perspectives"]["tha"]
    assert "worry" in out["perspectives"]["azc"]
