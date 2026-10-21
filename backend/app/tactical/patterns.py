"""Tactical pattern detection over sliding windows.

Detectors are deterministic and explainable: each returns the metrics it used and the event IDs that
support it. A small state machine turns frame-by-frame detections into START / END transitions so the
pipeline reacts to *changes* ("high press detected") rather than re-announcing a steady state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.data.teams import PLAYERS, player_name, team_name
from app.models.domain import EventType
from app.tactical.engine import TacticalEngine, channel, team_frame

E = EventType

ZONES = {  # team frame rectangles (x0, x1, y0, y1)
    "opp_defensive_third": (70, 105, 0, 68),
    "right_flank": (52.5, 105, 0, 22.7),
    "left_flank": (52.5, 105, 45.3, 68),
    "own_defensive_third": (0, 35, 0, 68),
    "midfield": (35, 70, 12, 56),
    "own_half": (0, 52.5, 0, 68),
}


@dataclass
class Pattern:
    type: str
    team_id: str
    confidence: float
    summary: str
    metrics: dict
    evidence_event_ids: list[str]
    zone: str
    players: list[str] = field(default_factory=list)
    started_minute: int = 0
    status: str = "active"

    @property
    def key(self) -> str:
        return f"{self.type}:{self.team_id}:{self.zone}"

    def to_dict(self) -> dict:
        return {"type": self.type, "team_id": self.team_id, "confidence": round(self.confidence, 2),
                "summary": self.summary, "metrics": self.metrics, "evidence_event_ids": self.evidence_event_ids,
                "zone": self.zone, "players": self.players, "started_minute": self.started_minute,
                "status": self.status}


def _conf(*scores: float) -> float:
    vals = [max(0.0, min(1.0, s)) for s in scores]
    return round(0.5 + 0.5 * (sum(vals) / len(vals)), 2)


# ------------------------------------------------------------------ threshold profiles
# "synthetic" was tuned on the generated demo match; "statsbomb" is produced by eval/calibrate.py from real
# World Cup / Euro matches so that each pattern fires only when its statistic is unusual (~top decile of windows).
DEFAULT_PROFILES: dict[str, dict] = {
    "synthetic": {"press_ppda_max": 4.5, "press_opp_half_min": 9, "press_defx_min": 56.0,
                  "flank_share_min": 0.55, "flank_actions_min": 14, "block_line_max": 23.0, "block_drop_min": 4.0,
                  "trans_fast_min": 3, "trans_ratio_min": 1.6, "trans_line_min": 31.0, "mid_avg_min": 1.6},
}
PROFILE_DIR = Path(__file__).parent / "profiles"


def load_profile(name: str) -> dict:
    f = PROFILE_DIR / f"{name}.json"
    if f.exists():
        return {**DEFAULT_PROFILES["synthetic"], **json.loads(f.read_text())["thresholds"]}
    return DEFAULT_PROFILES.get(name, DEFAULT_PROFILES["synthetic"])


# ------------------------------------------------------------------ features (shared by detectors and calibration)
def feat_press(engine: TacticalEngine, tid: str, ws: dict) -> dict | None:
    w = ws[tid]
    if w["ppda"] is None or w["avg_defensive_action_x"] is None:
        return None
    return {"ppda": w["ppda"], "opp_half": w["pressures_opp_half"], "defx": w["avg_defensive_action_x"]}


def feat_flank(engine: TacticalEngine, tid: str) -> dict | None:
    evs = [e for e in engine.window(420) if e.team_id == tid and e.type in (E.PASS, E.CARRY) and e.outcome == "success"]
    att = []
    for e in evs:
        end = engine.tf(e, end=True)
        if end and end[0] >= 52.5:
            att.append((e, channel(end[1])))
    if not att:
        return None
    counts = {c: sum(1 for _, ch in att if ch == c) for c in ("right", "left", "centre")}
    side = max(("right", "left"), key=lambda c: counts[c])
    return {"share": counts[side] / len(att), "actions": len(att), "side": side, "counts": counts, "att": att}


def feat_block(engine: TacticalEngine, tid: str) -> dict | None:
    now = engine.line_height_window(tid, 300)
    match = engine.totals()[tid]["defensive_line_height"]
    if now is None or match is None:
        return None
    return {"line": now, "drop": round(match - now, 2), "match": match}


def _fast_transitions(engine: TacticalEngine, tid: str, evs) -> list[tuple[str, str]]:
    """Counters by the opponent of `tid`: recovery in their own half → shot or entry to x≥80 within 12 s."""
    opp = engine.other(tid)
    out = []
    for i, e in enumerate(evs):
        if e.type != E.RECOVERY or e.team_id != opp:
            continue
        start = engine.tf(e)
        if not start or start[0] > 52.5:
            continue
        for f in evs[i + 1:]:
            dt = f.game_seconds - e.game_seconds
            if dt > 12 or dt < 0 or (f.team_id == tid and f.type in (E.RECOVERY, E.INTERCEPTION, E.TACKLE)):
                break
            end = engine.tf(f, end=True) or engine.tf(f)
            if f.team_id == opp and (f.type == E.SHOT or (end and end[0] >= 80)):
                out.append((e.event_id, f.event_id))
                break
    return out


def feat_transition(engine: TacticalEngine, tid: str) -> dict:
    recent = _fast_transitions(engine, tid, engine.window(600))
    minutes = max(10.0, engine.events[-1].game_seconds / 60)
    cache = engine.__dict__.setdefault("_ft_cache", {})
    if len(engine.events) % 40 == 0 or tid not in cache:
        cache[tid] = _fast_transitions(engine, tid, engine.events)
    base = len(cache[tid]) / minutes * 10
    return {"fast": len(recent), "baseline": base, "ratio": len(recent) / max(base, 0.5),
            "line": engine.line_height_window(tid, 300) or 0, "recent": recent}


def feat_midfield(engine: TacticalEngine, tid: str) -> dict | None:
    diffs, ids = [], []
    x0, x1, y0, y1 = ZONES["midfield"]
    for ev in engine.window(300):
        if not ev.positions or engine.possession_at(ev) != tid:
            continue
        mine = theirs = 0
        for p in ev.positions:
            fx, fy = team_frame(tid, engine.home, p.x, p.y)
            if x0 <= fx <= x1 and y0 <= fy <= y1:
                if p.team_id == tid:
                    mine += 1
                else:
                    theirs += 1
        diffs.append(mine - theirs)
        ids.append(ev.event_id)
    if len(diffs) < 25:
        return None
    return {"avg": sum(diffs) / len(diffs), "samples": len(diffs), "ids": ids}


def _span(v: float, lo: float, width: float) -> float:
    return (v - lo) / max(width, 1e-6)


# ------------------------------------------------------------------ detectors
def detect_high_press(engine: TacticalEngine, tid: str, ws: dict, th: dict) -> Pattern | None:
    f = feat_press(engine, tid, ws)
    if not f or not (f["ppda"] <= th["press_ppda_max"] and f["opp_half"] >= th["press_opp_half_min"]
                     and f["defx"] >= th["press_defx_min"]):
        return None
    w = ws[tid]
    ev = w["evidence"]["pressures"] + w["evidence"]["def_actions"]
    return Pattern("HIGH_PRESS", tid, _conf(_span(th["press_ppda_max"], f["ppda"], 3), _span(f["opp_half"], th["press_opp_half_min"], 10),
                                            _span(f["defx"], th["press_defx_min"], 15)),
                   f"{team_name(tid)} are pressing high: PPDA {f['ppda']} with {f['opp_half']} pressures in the opponent half "
                   f"over the last 5 minutes.",
                   {"ppda_5min": f["ppda"], "pressures_opp_half_5min": f["opp_half"], "avg_defensive_action_x": f["defx"],
                    "ppda_match": engine.totals()[tid]["ppda"]},
                   ev[-10:], "opp_defensive_third", players=_top_players(engine, ev, tid))


def detect_flank_overload(engine: TacticalEngine, tid: str, ws: dict, th: dict) -> Pattern | None:
    f = feat_flank(engine, tid)
    if not f or f["actions"] < th["flank_actions_min"] or f["share"] < th["flank_share_min"]:
        return None
    side, share = f["side"], f["share"]
    side_events = [e for e, ch in f["att"] if ch == side]
    players: dict[str, int] = {}
    for e in side_events:
        for pid in (e.player_id, e.related_player_id):
            if pid:
                players[pid] = players.get(pid, 0) + 1
    ranked = sorted(players, key=lambda p: -players[p])
    fullback = next((p for p in ranked[:4] if PLAYERS.get(p) and PLAYERS[p].position in ("RB", "LB")), None)
    extra = f" {player_name(fullback)} ({PLAYERS[fullback].position}) is repeatedly creating the overload." if fullback else ""
    return Pattern("FLANK_OVERLOAD", tid, _conf(_span(share, th["flank_share_min"] - 0.05, 0.3), _span(f["actions"], th["flank_actions_min"], 20)),
                   f"{team_name(tid)} are overloading the {side} flank: {round(share * 100)}% of their attacking-half "
                   f"actions in the last 7 minutes went down that side.{extra}",
                   {"flank_share_7min": round(share, 2), "attacking_actions_7min": f["actions"], "channel_counts": f["counts"],
                    "key_fullback": fullback},
                   [e.event_id for e in side_events[-10:]], f"{side}_flank", players=ranked[:3])


def detect_deep_block(engine: TacticalEngine, tid: str, ws: dict, th: dict) -> Pattern | None:
    f = feat_block(engine, tid)
    if not f or not (f["line"] <= th["block_line_max"] and f["drop"] >= th["block_drop_min"]):
        return None
    evs = [e.event_id for e in engine.window(300) if e.positions][-8:]
    return Pattern("DEEP_BLOCK", tid, _conf(_span(th["block_line_max"], f["line"], 6), _span(f["drop"], th["block_drop_min"], 6)),
                   f"{team_name(tid)} have dropped into a deep block: defensive line {f['line']} m from goal over the last "
                   f"5 minutes, {round(f['drop'], 1)} m deeper than their match average.",
                   {"line_height_5min": f["line"], "line_height_match": f["match"]}, evs, "own_defensive_third")


def detect_transition_vulnerability(engine: TacticalEngine, tid: str, ws: dict, th: dict) -> Pattern | None:
    """`tid` is the vulnerable team: the opponent repeatedly breaks from deep and arrives fast."""
    f = feat_transition(engine, tid)
    if not (f["fast"] >= th["trans_fast_min"] and f["ratio"] >= th["trans_ratio_min"] and f["line"] >= th["trans_line_min"]):
        return None
    opp = engine.other(tid)
    ids = [x for pair in f["recent"] for x in pair]
    return Pattern("TRANSITION_VULNERABILITY", tid,
                   _conf(_span(f["fast"], th["trans_fast_min"], 3), _span(f["ratio"], th["trans_ratio_min"], 2), _span(f["line"], th["trans_line_min"], 10)),
                   f"{team_name(tid)} are exposed in transition: {team_name(opp)} broke from their own half and "
                   f"reached the final third or shot within 12 s {f['fast']} times in the last 10 minutes "
                   f"(match rate {round(f['baseline'], 1)} per 10 min), against a {f['line']} m defensive line.",
                   {"fast_transitions_10min": f["fast"], "baseline_per_10min": round(f["baseline"], 2),
                    "line_height_5min": f["line"], "exploited_by": opp},
                   ids[-10:], "own_half", players=_top_players(engine, ids, opp))


def detect_midfield_superiority(engine: TacticalEngine, tid: str, ws: dict, th: dict) -> Pattern | None:
    f = feat_midfield(engine, tid)
    if not f or f["avg"] < th["mid_avg_min"]:
        return None
    return Pattern("MIDFIELD_SUPERIORITY", tid, _conf(_span(f["avg"], th["mid_avg_min"], 1.5), f["samples"] / 80),
                   f"{team_name(tid)} hold numerical superiority in midfield: on average +{round(f['avg'], 1)} players "
                   f"in the central zone while in possession (last 5 minutes).",
                   {"avg_central_superiority": round(f["avg"], 2), "samples": f["samples"]}, f["ids"][-8:], "midfield")


def _top_players(engine: TacticalEngine, event_ids: list[str], tid: str) -> list[str]:
    counts: dict[str, int] = {}
    for eid in event_ids:
        e = engine.by_id.get(eid)
        if e and e.player_id and e.team_id == tid:
            counts[e.player_id] = counts.get(e.player_id, 0) + 1
    return sorted(counts, key=lambda p: -counts[p])[:3]


DETECTORS = [detect_high_press, detect_flank_overload, detect_deep_block, detect_transition_vulnerability,
             detect_midfield_superiority]


class PatternTracker:
    """Hysteresis: a pattern must be detected on 3 consecutive checks to START and be absent for 25 checks to END."""

    START_HITS, END_MISSES = 3, 25

    def __init__(self, profile: str = "synthetic") -> None:
        self.profile = profile
        self.th = load_profile(profile)
        self.active: dict[str, Pattern] = {}
        self.hits: dict[str, int] = {}
        self.misses: dict[str, int] = {}
        self.history: list[dict] = []
        self.ended_at: dict[str, int] = {}

    def update(self, engine: TacticalEngine) -> list[tuple[str, Pattern]]:
        if not engine.events or engine.events[-1].minute < 4:
            return []
        ws = engine.window_stats(300)
        seen: dict[str, Pattern] = {}
        for tid in (engine.home, engine.away):
            for det in DETECTORS:
                p = det(engine, tid, ws, self.th)
                if p:
                    seen[p.key] = p
        changes: list[tuple[str, Pattern]] = []
        minute = engine.events[-1].minute
        for key, p in seen.items():
            self.misses[key] = 0
            if key in self.active:
                p.started_minute = self.active[key].started_minute
                self.active[key] = p
                continue
            self.hits[key] = self.hits.get(key, 0) + 1
            if self.hits[key] >= self.START_HITS:
                self.hits[key] = 0
                self.active[key] = p
                if minute - self.ended_at.get(key, -99) <= 4:  # flicker: treat as a continuation
                    p.started_minute = self.ended_at.pop(key, minute)
                    continue
                p.started_minute = minute
                self.history.append({**p.to_dict(), "event": "start", "minute": minute})
                changes.append(("start", p))
        for key in list(self.active):
            if key not in seen:
                self.misses[key] = self.misses.get(key, 0) + 1
                if self.misses[key] >= self.END_MISSES:
                    p = self.active.pop(key)
                    self.ended_at[key] = minute
                    p.status = "ended"
                    self.history.append({**p.to_dict(), "event": "end", "minute": minute})
                    changes.append(("end", p))
        for key in list(self.hits):
            if key not in seen:
                self.hits[key] = 0
        return changes

    def active_list(self) -> list[dict]:
        return [p.to_dict() for p in self.active.values()]
