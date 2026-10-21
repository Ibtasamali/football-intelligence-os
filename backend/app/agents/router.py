"""Significance scoring + Agent Router.

The router is the cost brain: for every event it decides which agents run, in which parallel waves,
whether memory and retrieval are needed, and which model tier (none / small / large) may be used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.models.domain import EventType

E = EventType

BASE = {E.GOAL: 1.0, E.SUBSTITUTION: 0.5, E.HALF_TIME: 0.0, E.FULL_TIME: 0.0, E.SAVE: 0.2, E.CORNER: 0.12,
        E.FOUL: 0.08, E.OFFSIDE: 0.08, E.PRESSURE: 0.02, E.PASS: 0.02, E.CARRY: 0.02, E.TACKLE: 0.06,
        E.INTERCEPTION: 0.06, E.RECOVERY: 0.05, E.POSSESSION_CHANGE: 0.0, E.KICK_OFF: 0.0}


def score_event(ev, delta: dict, pattern_changes: list, minute: int, score_diff: int) -> tuple[float, str, list[str]]:
    """Return (significance 0–1, category, reasons). Pure function, no I/O."""
    reasons = []
    s = BASE.get(ev.type, 0.05)
    cat = "ROUTINE"
    if ev.type == E.GOAL:
        cat = "GOAL"
        reasons.append("goal")
    elif ev.type == E.SHOT:
        xg = float(ev.meta.get("xg", 0))
        s = 0.3 + min(0.5, xg * 1.3)
        cat = "DANGEROUS_ATTACK"
        reasons.append(f"shot xG {xg}")
    elif ev.type == E.CARD:
        s = 0.75 if ev.outcome == "red" else 0.35
        cat = "PLAYER_IMPACT"
        reasons.append(f"{ev.outcome} card")
    elif ev.type == E.SUBSTITUTION:
        cat = "TACTICAL_SHIFT"
        reasons.append("substitution")
    elif ev.type == E.RECOVERY and delta.get("high_turnover"):
        s = 0.42
        cat = "HIGH_PRESS"
        reasons.append("high turnover")
    if delta.get("final_third_entry"):
        s = max(s, 0.1)
    starts = [p for kind, p in pattern_changes if kind == "start"]
    if starts:
        s = max(s, 0.7)
        cat = {"HIGH_PRESS": "HIGH_PRESS", "TRANSITION_VULNERABILITY": "TURNING_POINT"}.get(starts[0].type, "TACTICAL_SHIFT")
        reasons.append(f"pattern start: {', '.join(p.type for p in starts)}")
    elif any(kind == "end" for kind, _ in pattern_changes):
        s = max(s, 0.3)
        reasons.append("pattern ended")
    swing = abs(delta.get("momentum_after", 0) - delta.get("momentum_before", 0))
    if swing >= 0.18:
        s += 0.15
        reasons.append(f"momentum swing {round(swing, 2)}")
        if cat == "ROUTINE":
            cat = "MOMENTUM_SHIFT"
    if minute >= 75 and abs(score_diff) <= 1 and s >= 0.25:
        s *= 1.15
        reasons.append("late, close game")
    return round(min(1.0, s), 3), cat, reasons


@dataclass
class RoutingPlan:
    waves: list[list[str]] = field(default_factory=list)
    needs_memory: bool = False
    needs_retrieval: bool = False
    model_tier: str = "none"
    retrieval_reason: str = ""
    reasons: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


PATTERN_AGENTS = {
    "HIGH_PRESS": ["pressing_analysis", "space_analysis", "defensive_analysis"],
    "FLANK_OVERLOAD": ["attacking_analysis", "space_analysis", "passing_network", "player_intelligence"],
    "DEEP_BLOCK": ["defensive_analysis", "formation", "attacking_analysis"],
    "TRANSITION_VULNERABILITY": ["defensive_analysis", "space_analysis", "pressing_analysis"],
    "MIDFIELD_SUPERIORITY": ["formation", "passing_network", "team_intelligence"],
}

ALL_ANALYSIS = ["formation", "goal_probability", "tactical_analysis", "defensive_analysis", "attacking_analysis",
                "passing_network", "space_analysis", "pressing_analysis", "substitution_impact",
                "player_intelligence", "team_intelligence"]


def plan_event(ev, significance: float, category: str, new_patterns: list[dict], large_threshold: float) -> RoutingPlan:
    plan = RoutingPlan()
    wave1 = ["cag_context", "match_intelligence", "event_interpretation", "momentum"]
    wave2: list[str] = []
    t = ev.type
    if t in (E.SHOT, E.GOAL, E.SAVE):
        wave2 += ["goal_probability", "attacking_analysis", "player_intelligence"]
        if t == E.GOAL:
            wave2 += ["passing_network", "space_analysis", "team_intelligence"]
    if t in (E.RECOVERY, E.INTERCEPTION, E.TACKLE):
        wave2 += ["pressing_analysis", "space_analysis", "defensive_analysis"]
    if t == E.SUBSTITUTION:
        wave2 += ["substitution_impact", "formation", "team_intelligence", "player_intelligence"]
    if t in (E.CARD, E.FOUL):
        wave2 += ["player_intelligence"]
    for p in new_patterns:
        wave2 += ["tactical_analysis"] + PATTERN_AGENTS.get(p["type"], [])
    if not wave2:
        wave2 = ["tactical_analysis"]
    wave2 = list(dict.fromkeys(wave2))
    plan.waves = [wave1, wave2]
    plan.skipped = [a for a in ALL_ANALYSIS if a not in wave2]

    plan.needs_memory = bool(new_patterns) or t in (E.GOAL, E.SUBSTITUTION)
    plan.needs_retrieval = bool(new_patterns) or t == E.GOAL
    plan.retrieval_reason = "pattern_start" if new_patterns else ("goal" if t == E.GOAL else "")
    if significance >= large_threshold:
        plan.model_tier = "large"
    elif significance >= 0.45:
        plan.model_tier = "small"
    else:
        plan.model_tier = "none"
    plan.reasons = [f"significance {significance} → model tier '{plan.model_tier}'",
                    f"memory {'needed' if plan.needs_memory else 'not needed'}",
                    f"retrieval {'needed' if plan.needs_retrieval else 'not needed (CAG sufficient)'}",
                    f"{len(wave1) + len(wave2)} analysis agents scheduled, {len(plan.skipped)} skipped"]
    return plan


QUERY_AGENTS = {
    "WHAT_HAPPENED": ["event_interpretation", "tactical_analysis"],
    "WHY": ["tactical_analysis", "pressing_analysis", "space_analysis", "defensive_analysis"],
    "BEST_PLAYER": ["player_intelligence", "passing_network"],
    "COMPARE": ["tactical_analysis", "attacking_analysis"],
    "SIMILAR": ["tactical_analysis"],
    "PREDICT": ["tactical_analysis", "goal_probability"],
    "STATS": ["team_intelligence", "goal_probability"],
    "MOMENTUM": ["team_intelligence"],
    "TACTICS": ["tactical_analysis", "formation", "pressing_analysis", "attacking_analysis"],
    "STORY": ["team_intelligence", "player_intelligence", "substitution_impact"],
    "GENERAL": ["tactical_analysis", "team_intelligence"],
}


def plan_query(intent: str, cag_sufficient: bool) -> RoutingPlan:
    plan = RoutingPlan()
    plan.waves = [["cag_context", "match_intelligence", "momentum"], QUERY_AGENTS.get(intent, QUERY_AGENTS["GENERAL"])]
    plan.needs_memory = intent in ("SIMILAR", "COMPARE", "WHY", "GENERAL", "BEST_PLAYER", "STORY")
    plan.needs_retrieval = intent in ("SIMILAR", "COMPARE") or (intent in ("WHY", "TACTICS", "GENERAL") and not cag_sufficient)
    plan.retrieval_reason = "question"
    plan.model_tier = "large" if intent in ("COMPARE", "STORY") else "small"
    plan.reasons = [f"intent {intent}", f"CAG {'sufficient' if cag_sufficient else 'insufficient'}",
                    f"retrieval {'needed' if plan.needs_retrieval else 'skipped'}", f"tier {plan.model_tier}"]
    return plan
