"""What-if tactical sandbox: recompute space, threat and passing options for a counterfactual player layout.

Pitch control is a simplified time-to-reach model in the spirit of Spearman (2018) / Fernández & Bornn (2018):
for every grid cell each player's arrival time is reaction + distance / speed; the attacking team's control of the
cell is a logistic function of (fastest defender time − fastest attacker time). Dangerous space weights controlled
cells by the xG of a shot from that cell (our fitted xG model), so moving a defender changes a single, explainable
number: how much goal-threatening space the attackers own.
"""
from __future__ import annotations

import math

import numpy as np

from app.data.teams import PLAYERS, player_name, team_name
from app.tactical.xg import expected_goals

L, W = 105.0, 68.0
NX, NY = 30, 20                       # 3.5 m × 3.4 m cells
REACTION, SPEED, SIGMA = 0.7, 7.0, 0.45

_xs = (np.arange(NX) + 0.5) * L / NX
_ys = (np.arange(NY) + 0.5) * W / NY
_GX, _GY = np.meshgrid(_xs, _ys)       # shape (NY, NX), absolute coordinates


def _value_grid(attacking_home: bool) -> np.ndarray:
    """xG of a shot from each cell, in the attacking team's frame (home attacks towards x = 105)."""
    v = np.zeros((NY, NX))
    for j, y in enumerate(_ys):
        for i, x in enumerate(_xs):
            tx, ty = (x, y) if attacking_home else (L - x, W - y)
            v[j, i] = expected_goals(tx, ty) if tx > 60 else 0.0
    return v


_VALUE = {True: _value_grid(True), False: _value_grid(False)}


def pitch_control(positions: list[dict], attacking: str) -> np.ndarray:
    """P(attacking team controls cell), shape (NY, NX)."""
    def fastest(team_pts):
        if not team_pts:
            return np.full((NY, NX), 99.0)
        t = [REACTION + np.hypot(_GX - x, _GY - y) / SPEED for x, y in team_pts]
        return np.min(np.stack(t), axis=0)
    att = [(p["x"], p["y"]) for p in positions if p["team_id"] == attacking]
    dfd = [(p["x"], p["y"]) for p in positions if p["team_id"] != attacking]
    return 1 / (1 + np.exp(-(fastest(dfd) - fastest(att)) / SIGMA))


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-9
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def passing_options(positions: list[dict], attacking: str, carrier: str | None) -> list[dict]:
    pos = {p["player_id"]: p for p in positions}
    if not carrier or carrier not in pos:
        return []
    c = pos[carrier]
    out = []
    for p in positions:
        if p["team_id"] != attacking or p["player_id"] == carrier:
            continue
        dist = math.hypot(p["x"] - c["x"], p["y"] - c["y"])
        if dist > 42 or dist < 3:
            continue
        blocked = any(_seg_dist(o["x"], o["y"], c["x"], c["y"], p["x"], p["y"]) < 1.8
                      for o in positions if o["team_id"] != attacking)
        out.append({"to": p["player_id"], "name": player_name(p["player_id"]), "open": not blocked, "distance": round(dist, 1),
                    "from_xy": [c["x"], c["y"]], "to_xy": [p["x"], p["y"]]})
    return out


def _line_and_shape(positions: list[dict], team: str, home: str) -> dict:
    pts = [((p["x"] if team == home else L - p["x"]), (p["y"] if team == home else W - p["y"]))
           for p in positions if p["team_id"] == team]
    pts = sorted(pts)[1:]  # drop goalkeeper (deepest)
    if len(pts) < 8:
        return {}
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"line_height": round(sum(xs[:4]) / 4, 1), "compactness_m2": round((max(xs) - min(xs)) * (max(ys) - min(ys))),
            "width": round(max(ys) - min(ys), 1)}


def _channels(positions: list[dict], attacking: str, home: str) -> dict:
    out = {}
    for ch, (y0, y1) in {"right": (0, 22.7), "centre": (22.7, 45.3), "left": (45.3, 68)}.items():
        a = d = 0
        for p in positions:
            fx, fy = (p["x"], p["y"]) if attacking == home else (L - p["x"], W - p["y"])
            if fx >= 52.5 and y0 <= fy < y1:
                a += p["team_id"] == attacking
                d += p["team_id"] != attacking
        out[ch] = f"{a}v{d}"
    return out


def evaluate(positions: list[dict], attacking: str, home: str, carrier: str | None) -> tuple[dict, np.ndarray]:
    ctrl = pitch_control(positions, attacking)
    value = _VALUE[attacking == home]
    danger = float((ctrl * value).sum())
    max_danger = float(value.sum()) or 1.0
    final_third = (_GX >= 70) if attacking == home else (_GX <= 35)
    cell_area = (L / NX) * (W / NY)
    defending = next((p["team_id"] for p in positions if p["team_id"] != attacking), None)
    opts = passing_options(positions, attacking, carrier)
    metrics = {
        "dangerous_space_pct": round(100 * danger / max_danger, 1),
        "final_third_space_m2": round(float((ctrl * final_third).sum()) * cell_area),
        "pitch_control_pct": round(100 * float(ctrl.mean()), 1),
        "open_passing_options": sum(1 for o in opts if o["open"]),
        "passing_options": opts,
        "attack_shape": _line_and_shape(positions, attacking, home),
        "defence_shape": _line_and_shape(positions, defending, home) if defending else {},
        "channels": _channels(positions, attacking, home),
    }
    return metrics, ctrl


def simulate(event, home: str, attacking: str, moves: dict[str, list[float]]) -> dict:
    before_pos = [p.model_dump() for p in event.positions]
    after_pos = []
    for p in before_pos:
        q = dict(p)
        if p["player_id"] in moves:
            q["x"] = max(0.0, min(L, float(moves[p["player_id"]][0])))
            q["y"] = max(0.0, min(W, float(moves[p["player_id"]][1])))
        after_pos.append(q)
    carrier = event.player_id if event.team_id == attacking else None
    if carrier is None:  # nearest attacker to the ball
        bx, by = (event.end_x or event.x or 52.5), (event.end_y or event.y or 34)
        att = [p for p in before_pos if p["team_id"] == attacking]
        carrier = min(att, key=lambda p: math.hypot(p["x"] - bx, p["y"] - by))["player_id"] if att else None
    before, cb = evaluate(before_pos, attacking, home, carrier)
    after, ca = evaluate(after_pos, attacking, home, carrier)
    delta = {
        "dangerous_space_pct": round(after["dangerous_space_pct"] - before["dangerous_space_pct"], 1),
        "final_third_space_m2": after["final_third_space_m2"] - before["final_third_space_m2"],
        "pitch_control_pct": round(after["pitch_control_pct"] - before["pitch_control_pct"], 1),
        "open_passing_options": after["open_passing_options"] - before["open_passing_options"],
    }
    moved = []
    for pid, xy in moves.items():
        orig = next((p for p in before_pos if p["player_id"] == pid), None)
        if orig:
            moved.append({"player_id": pid, "name": player_name(pid), "team": team_name(PLAYERS[pid].team_id) if pid in PLAYERS else "",
                          "attacking_team": PLAYERS.get(pid) and PLAYERS[pid].team_id == attacking,
                          "moved_m": round(math.hypot(xy[0] - orig["x"], xy[1] - orig["y"]), 1),
                          "from": [orig["x"], orig["y"]], "to": xy})
    return {"attacking_team": attacking, "attacking_name": team_name(attacking), "carrier": carrier,
            "carrier_name": player_name(carrier) if carrier else None, "moved": moved,
            "before": before, "after": after, "delta": delta,
            "grid": {"nx": NX, "ny": NY, "control_before": np.round(cb, 2).tolist(), "control_after": np.round(ca, 2).tolist()}}
