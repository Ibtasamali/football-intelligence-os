"""3D Visualization Agent output: declarative scene commands the R3F stadium executes.

Commands are data, not code, so they can be stored (`visualization_commands`), replayed from the
timeline and diffed between two situations for historical comparison.
"""
from __future__ import annotations

from app.data.teams import TEAMS
from app.tactical.patterns import ZONES

L, W = 105.0, 68.0

PATTERN_COLORS = {"HIGH_PRESS": "#FACC15", "FLANK_OVERLOAD": "#22D3EE", "DEEP_BLOCK": "#A78BFA",
                  "TRANSITION_VULNERABILITY": "#F97316", "MIDFIELD_SUPERIORITY": "#34D399"}


def zone_abs(zone: str, team_id: str, home_id: str) -> dict:
    x0, x1, y0, y1 = ZONES.get(zone, (0, L, 0, W))
    if team_id != home_id:
        x0, x1, y0, y1 = L - x1, L - x0, W - y1, W - y0
    return {"x0": round(x0, 1), "x1": round(x1, 1), "y0": round(y0, 1), "y1": round(y1, 1)}


def trajectories(events: list) -> list[dict]:
    out = []
    for e in events:
        if e.x is None:
            continue
        if e.end_x is not None and e.type.value in ("PASS", "CARRY", "SHOT"):
            out.append({"type": "trajectory", "kind": e.type.value.lower(), "event_id": e.event_id,
                        "from": [e.x, e.y], "to": [e.end_x, e.end_y], "success": e.outcome in ("success", "goal", "saved"),
                        "team_id": e.team_id})
    return out


def commands_for_insight(*, category: str, team_id: str | None, home_id: str, patterns: list[dict], events: list,
                         player_ids: list[str], network: list[dict] | None = None,
                         positions_lookup=None) -> list[dict]:
    cmds: list[dict] = []
    color = TEAMS[team_id].colors["primary"] if team_id in TEAMS else "#ffffff"
    focus = None
    for p in patterns[:2]:
        z = zone_abs(p["zone"], p["team_id"], home_id)
        cmds.append({"type": "highlight_zone", "zone": z, "color": PATTERN_COLORS.get(p["type"], color),
                     "label": p["type"].replace("_", " ").title(), "team_id": p["team_id"]})
        focus = focus or [(z["x0"] + z["x1"]) / 2, (z["y0"] + z["y1"]) / 2]
        if p["type"] in ("DEEP_BLOCK", "TRANSITION_VULNERABILITY") and "line_height_5min" in p["metrics"]:
            lh = p["metrics"]["line_height_5min"]
            cmds.append({"type": "defensive_line", "team_id": p["team_id"],
                         "x": lh if p["team_id"] == home_id else L - lh, "label": f"Line {lh} m"})
        player_ids = list(dict.fromkeys(player_ids + p.get("players", [])))
    if player_ids:
        cmds.append({"type": "highlight_players", "player_ids": player_ids[:6], "color": color})
    traj = trajectories(events[-8:])
    cmds.extend(traj)
    if network and positions_lookup:
        lanes = []
        for n in network[:6]:
            a, b = positions_lookup(n["from"]), positions_lookup(n["to"])
            if a and b:
                lanes.append({"from": a, "to": b, "count": n["count"], "from_id": n["from"], "to_id": n["to"]})
        if lanes:
            cmds.append({"type": "passing_lanes", "lanes": lanes, "color": color})
    shot = next((e for e in reversed(events) if e.type.value in ("SHOT", "GOAL") and e.x is not None), None)
    if shot:
        cmds.append({"type": "pulse", "at": [shot.x, shot.y], "color": "#FDE047" if category == "GOAL" else color,
                     "label": f"xG {shot.meta.get('xg')}" if shot.meta.get("xg") is not None else ""})
        focus = focus or [shot.x, shot.y]
    if not focus and events and events[-1].x is not None:
        focus = [events[-1].x, events[-1].y]
    cmds.append({"type": "camera", "preset": "tactical" if patterns else "broadcast", "focus": focus or [52.5, 34]})
    if events:
        cmds.append({"type": "replay", "event_ids": [e.event_id for e in events[-12:]]})
    return cmds
