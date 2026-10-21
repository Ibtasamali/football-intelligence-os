"""Probabilistic predictions. Every output is labelled as a prediction with its basis.

- Next-action model: empirical Markov chain of event-type transitions observed *in this match*
  (Laplace-smoothed), so it adapts to how the game is actually being played.
- Goal-threat model: logistic blend of recent xG, field tilt, momentum and active patterns,
  converted into P(at least one goal in the next 10 minutes) via a Poisson rate.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from app.data.teams import team_name
from app.models.domain import Prediction
from app.tactical.engine import TacticalEngine

TRACKED = ["PASS", "CARRY", "SHOT", "PRESSURE", "INTERCEPTION", "TACKLE", "FOUL", "CORNER", "RECOVERY"]


def next_action_distribution(engine: TacticalEngine, current_type: str, top: int = 3) -> list[tuple[str, float]]:
    row = {b: c for (a, b), c in engine.transitions_matrix.items() if a == current_type and b in TRACKED}
    total = sum(row.values()) + len(TRACKED)
    dist = sorted(((b, (row.get(b, 0) + 1) / total) for b in TRACKED), key=lambda kv: -kv[1])
    return [(b, round(p, 3)) for b, p in dist[:top]]


_FITTED = Path(__file__).with_name("fitted.json")
_GT = json.loads(_FITTED.read_text()).get("goal_threat") if _FITTED.exists() else None


def _pattern_adj(team_id: str, active_patterns: list[dict]) -> float:
    adj = 0.0
    for p in active_patterns:
        if p["type"] in ("HIGH_PRESS", "FLANK_OVERLOAD", "MIDFIELD_SUPERIORITY") and p["team_id"] == team_id:
            adj += 0.25
        if p["type"] == "TRANSITION_VULNERABILITY" and p["team_id"] != team_id:
            adj += 0.4
        if p["type"] == "DEEP_BLOCK" and p["team_id"] != team_id:
            adj -= 0.15
    return adj


def goal_features(engine: TacticalEngine, team_id: str, active_patterns: list[dict]) -> dict:
    """Live features for the goal-threat model (shared by the runtime and eval/fit_models.py)."""
    ws = engine.window_stats(600)
    me, opp = ws[team_id], ws[engine.other(team_id)]
    minute = engine.events[-1].minute if engine.events else 0
    return {"xg_10": me["xg"], "opp_xg_10": opp["xg"], "shots_10": me["shots"], "field_tilt_10": me["field_tilt"],
            "momentum": engine.momentum_index() * (1 if team_id == engine.home else -1),
            "pattern_adj": _pattern_adj(team_id, active_patterns),
            "score_diff": engine.score[team_id] - engine.score[engine.other(team_id)], "minute": minute / 90}


def goal_threat(engine: TacticalEngine, team_id: str, active_patterns: list[dict]) -> dict:
    if _GT:
        f = goal_features(engine, team_id, active_patterns)
        z = _GT["weights"][0] + sum(w * (f[k] - m) / s for k, w, m, s in
                                    zip(_GT["features"], _GT["weights"][1:], _GT["mean"], _GT["std"]))
        p10 = 1 / (1 + math.exp(-z))
        return {"team_id": team_id, "p_goal_next_10": round(p10, 3),
                "model": f"low-resolution logistic estimate (fitted on real matches, CV AUC {_GT.get('cv_auc', '?')})", "inputs": {
            "xg_10min": f["xg_10"], "field_tilt_10min": f["field_tilt_10"], "momentum": round(f["momentum"], 2),
            "pattern_adjustment": round(f["pattern_adj"], 2)}}
    return _goal_threat_handset(engine, team_id, active_patterns)


def _goal_threat_handset(engine: TacticalEngine, team_id: str, active_patterns: list[dict]) -> dict:
    ws = engine.window_stats(600)[team_id]
    mom = engine.momentum_index() * (1 if team_id == engine.home else -1)
    pattern_boost = 0.0
    for p in active_patterns:
        if p["type"] in ("HIGH_PRESS", "FLANK_OVERLOAD", "MIDFIELD_SUPERIORITY") and p["team_id"] == team_id:
            pattern_boost += 0.25
        if p["type"] == "TRANSITION_VULNERABILITY" and p["team_id"] != team_id:
            pattern_boost += 0.4
        if p["type"] == "DEEP_BLOCK" and p["team_id"] != team_id:
            pattern_boost -= 0.15
    # baseline: ~1.35 goals / 90 min per team
    base_rate = 1.35 / 90
    rate = base_rate * math.exp(1.1 * ws["xg"] + 0.9 * (ws["field_tilt"] - 0.5) + 0.8 * mom + pattern_boost)
    rate = min(rate, 0.06)
    p10 = 1 - math.exp(-rate * 10)
    return {"team_id": team_id, "p_goal_next_10": round(p10, 3), "inputs": {
        "xg_10min": ws["xg"], "field_tilt_10min": ws["field_tilt"], "momentum": round(mom, 2),
        "pattern_adjustment": round(pattern_boost, 2)}}


def predict(engine: TacticalEngine, current_type: str, active_patterns: list[dict]) -> list[Prediction]:
    out: list[Prediction] = []
    for tid in (engine.home, engine.away):
        g = goal_threat(engine, tid, active_patterns)
        out.append(Prediction(
            label=f"{team_name(tid)} score in the next 10 minutes", probability=g["p_goal_next_10"],
            horizon="10 min", basis=f"{g.get('model', 'Poisson rate')} from 10-min xG {g['inputs']['xg_10min']}, field tilt "
                                    f"{g['inputs']['field_tilt_10min']}, momentum {g['inputs']['momentum']}, "
                                    f"pattern adj. {g['inputs']['pattern_adjustment']}"))
    dist = next_action_distribution(engine, current_type)
    if dist:
        b, p = dist[0]
        out.append(Prediction(label=f"Next action: {b.lower().replace('_', ' ')}", probability=p, horizon="next event",
                              basis=f"Markov transition frequencies from {current_type} observed in this match"))
    for p in active_patterns:
        if p["type"] == "TRANSITION_VULNERABILITY":
            exploiter = p["metrics"].get("exploited_by")
            prob = min(0.85, 0.35 + 0.08 * p["metrics"].get("fast_transitions_10min", 0))
            out.append(Prediction(label=f"{team_name(exploiter)} create a dangerous counter-attack in the next 5 min",
                                  probability=round(prob, 2), horizon="5 min",
                                  basis=f"{p['metrics']['fast_transitions_10min']} fast transitions in 10 min vs "
                                        f"match rate {p['metrics']['baseline_per_10min']}"))
    return out


def substitution_impact(engine: TacticalEngine, sub: dict, window_s: int = 600) -> dict | None:
    """Compare the subbing team's output in equal windows before/after the substitution."""
    t = sub["minute"] * 60
    now = engine.events[-1].game_seconds if engine.events else 0
    if now - t < 240:
        return None
    span = min(window_s, now - t)
    tid = sub["team_id"]

    def agg(t0, t1):
        evs = [e for e in engine.events if t0 <= e.game_seconds < t1 and e.team_id == tid]
        return {"xg": round(sum(float(e.meta.get("xg", 0)) for e in evs if e.type.value == "SHOT"), 2),
                "final_third_entries": sum(1 for e in evs if e.type.value in ("PASS", "CARRY")
                                           and (en := engine.tf(e, end=True)) and (st := engine.tf(e))
                                           and st[0] < 70 <= en[0]),
                "player_on_involvements": sum(1 for e in evs if sub["on"] in (e.player_id, e.related_player_id))}

    return {"before": agg(t - span, t), "after": agg(t, t + span), "window_minutes": round(span / 60, 1)}
