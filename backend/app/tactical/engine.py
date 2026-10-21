"""Incremental tactical metrics engine.

Consumes events in order and maintains every metric the agents talk about. All numbers that appear in
AI insights are read from here (and are therefore verifiable by the Fact Verification agent).
Coordinates are converted into each team's attacking frame (own goal at x=0).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from app.models.domain import EventType, MatchEvent

L, W = 105.0, 68.0
E = EventType
DEF_ACTIONS = {E.TACKLE, E.INTERCEPTION, E.FOUL}
MOMENTUM_HALF_LIFE = 180.0  # seconds of game time


def team_frame(team_id: str, home_id: str, x: float | None, y: float | None) -> tuple[float, float] | None:
    if x is None or y is None:
        return None
    return (x, y) if team_id == home_id else (L - x, W - y)


def dist_to_goal(tx: float, ty: float) -> float:
    return math.hypot(L - tx, ty - W / 2)


def channel(ty: float) -> str:
    return "right" if ty < 22.7 else "left" if ty > 45.3 else "centre"


@dataclass
class TeamStats:
    passes: int = 0
    passes_completed: int = 0
    touches: int = 0
    progressive_passes: int = 0
    progressive_carries: int = 0
    final_third_entries: int = 0
    shots: int = 0
    shots_on_target: int = 0
    xg: float = 0.0
    big_chances: int = 0
    goals: int = 0
    defensive_actions: int = 0
    pressures: int = 0
    high_turnovers: int = 0
    corners: int = 0
    fouls: int = 0
    cards: int = 0
    final_third_passes: int = 0
    ppda_opp_passes: int = 0
    ppda_def_actions: int = 0
    line_height_sum: float = 0.0
    line_height_n: int = 0
    compact_sum: float = 0.0
    compact_n: int = 0
    width_sum: float = 0.0
    width_n: int = 0
    transitions: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "passes": self.passes,
            "pass_completion": round(self.passes_completed / self.passes, 3) if self.passes else 0.0,
            "progressive_passes": self.progressive_passes,
            "progressive_carries": self.progressive_carries,
            "final_third_entries": self.final_third_entries,
            "shots": self.shots,
            "shots_on_target": self.shots_on_target,
            "xg": round(self.xg, 2),
            "big_chances": self.big_chances,
            "goals": self.goals,
            "defensive_actions": self.defensive_actions,
            "pressures": self.pressures,
            "high_turnovers": self.high_turnovers,
            "corners": self.corners,
            "fouls": self.fouls,
            "ppda": round(self.ppda_opp_passes / self.ppda_def_actions, 2) if self.ppda_def_actions else None,
            "defensive_line_height": round(self.line_height_sum / self.line_height_n, 1) if self.line_height_n else None,
            "compactness_m2": round(self.compact_sum / self.compact_n) if self.compact_n else None,
            "attacking_width": round(self.width_sum / self.width_n, 1) if self.width_n else None,
            "avg_transition_seconds": round(sum(self.transitions) / len(self.transitions), 1) if self.transitions else None,
        }


class TacticalEngine:
    def __init__(self, match_id: str, home_id: str, away_id: str) -> None:
        self.match_id = match_id
        self.home, self.away = home_id, away_id
        self.stats = {home_id: TeamStats(), away_id: TeamStats()}
        self.events: list[MatchEvent] = []
        self.by_id: dict[str, MatchEvent] = {}
        self.score = {home_id: 0, away_id: 0}
        self.network: dict[str, Counter] = {home_id: Counter(), away_id: Counter()}
        self.player: dict[str, Counter] = defaultdict(Counter)
        self.momentum = {home_id: 0.0, away_id: 0.0}
        self.momentum_history: deque = deque(maxlen=400)
        self.possession_team: str | None = None
        self.last_recovery: dict[str, tuple[int, str]] = {}
        self.substitutions: list[dict] = []
        self.transitions_matrix: Counter = Counter()
        self._last_t = 0

    # ---------------------------------------------------------------- helpers
    def other(self, team_id: str) -> str:
        return self.away if team_id == self.home else self.home

    def tf(self, ev: MatchEvent, end: bool = False):
        if not ev.team_id:
            return None
        return team_frame(ev.team_id, self.home, ev.end_x if end else ev.x, ev.end_y if end else ev.y)

    def _decay(self, t: int) -> None:
        dt = max(0, t - self._last_t)
        if dt:
            f = 0.5 ** (dt / MOMENTUM_HALF_LIFE)
            for k in self.momentum:
                self.momentum[k] *= f
        self._last_t = t

    def momentum_index(self) -> float:
        h, a = self.momentum[self.home], self.momentum[self.away]
        return round((h - a) / (h + a + 0.6), 3)

    # ---------------------------------------------------------------- update
    def update(self, ev: MatchEvent) -> dict:
        """Apply one event. Returns a small delta used by significance scoring."""
        if self.events:
            self.transitions_matrix[(self.events[-1].type.value, ev.type.value)] += 1
        self.events.append(ev)
        self.by_id[ev.event_id] = ev
        self._decay(ev.game_seconds)
        before = self.momentum_index()
        delta: dict = {"threat": 0.0, "progressive": False, "final_third_entry": False, "high_turnover": False}
        tid = ev.team_id
        if tid not in self.stats:
            if ev.type in (E.HALF_TIME, E.FULL_TIME):
                delta["momentum_before"] = before
                delta["momentum_after"] = before
            return delta
        st, opp = self.stats[tid], self.stats[self.other(tid)]
        start, end = self.tf(ev), self.tf(ev, end=True)
        if ev.player_id:
            self.player[ev.player_id]["involvements"] += 1

        if ev.type in (E.PASS, E.CARRY, E.SHOT):
            st.touches += 1
            self.possession_team = tid

        if ev.type == E.PASS:
            st.passes += 1
            if start and start[0] <= 63:
                opp.ppda_opp_passes += 1
            if start and start[0] >= 70:
                st.final_third_passes += 1
            if ev.outcome == "success":
                st.passes_completed += 1
                self.player[ev.player_id]["passes_completed"] += 1
                if ev.related_player_id:
                    self.network[tid][(ev.player_id, ev.related_player_id)] += 1
                    self.player[ev.related_player_id]["receptions"] += 1
                if start and end:
                    delta.update(self._progression(st, ev, start, end, carry=False))
        elif ev.type == E.CARRY and ev.outcome == "success" and start and end:
            delta.update(self._progression(st, ev, start, end, carry=True))
        elif ev.type == E.SHOT:
            xg = float(ev.meta.get("xg", 0.0))
            st.shots += 1
            st.xg += xg
            self.player[ev.player_id]["shots"] += 1
            self.player[ev.player_id]["xg_milli"] += int(xg * 1000)
            if ev.related_player_id:
                self.player[ev.related_player_id]["xa_milli"] += int(xg * 1000)
            if ev.meta.get("big_chance"):
                st.big_chances += 1
            if ev.outcome in ("goal", "saved"):
                st.shots_on_target += 1
            delta["threat"] += 0.4 + 3.0 * xg
            self._transition_close(tid, ev)
        elif ev.type == E.GOAL:
            st.goals += 1
            self.score[tid] += 1
            self.player[ev.player_id]["goals"] += 1
            if ev.related_player_id:
                self.player[ev.related_player_id]["assists"] += 1
            delta["threat"] += 1.0
        elif ev.type in DEF_ACTIONS:
            if ev.type != E.FOUL:
                st.defensive_actions += 1
                self.player[ev.player_id]["defensive_actions"] += 1
            else:
                st.fouls += 1
            if start and start[0] >= 42:
                st.ppda_def_actions += 1
        elif ev.type == E.PRESSURE:
            st.pressures += 1
            self.player[ev.player_id]["pressures"] += 1
            delta["threat"] += 0.05
        elif ev.type == E.RECOVERY:
            self.last_recovery[tid] = (ev.game_seconds, ev.event_id)
            self.player[ev.player_id]["recoveries"] += 1
            if start and start[0] >= 65:
                st.high_turnovers += 1
                delta["high_turnover"] = True
                delta["threat"] += 0.45
            self.possession_team = tid
        elif ev.type == E.CORNER:
            st.corners += 1
            delta["threat"] += 0.15
        elif ev.type == E.CARD:
            st.cards += 1
        elif ev.type == E.SUBSTITUTION:
            self.substitutions.append({"minute": ev.minute, "team_id": tid, "on": ev.player_id,
                                       "off": ev.related_player_id, "reason": ev.meta.get("reason", ""),
                                       "event_id": ev.event_id, "momentum_at_sub": self.momentum_index()})

        self._shape(ev)
        self.momentum[tid] += delta["threat"]
        after = self.momentum_index()
        self.momentum_history.append((ev.game_seconds, after))
        delta["momentum_before"], delta["momentum_after"] = before, after
        return delta

    def _progression(self, st: TeamStats, ev: MatchEvent, start, end, carry: bool) -> dict:
        out = {}
        d0, d1 = dist_to_goal(*start), dist_to_goal(*end)
        if end[0] >= 42 and d0 - d1 >= 0.25 * d0 and d0 - d1 >= 8:
            if carry:
                st.progressive_carries += 1
            else:
                st.progressive_passes += 1
            self.player[ev.player_id]["progressive_actions"] += 1
            out["progressive"] = True
            out["threat"] = 0.12
        if start[0] < 70 <= end[0]:
            st.final_third_entries += 1
            out["final_third_entry"] = True
            out["threat"] = out.get("threat", 0.0) + 0.18
            self._transition_close(ev.team_id, ev)
        return out

    def _transition_close(self, team_id: str, ev: MatchEvent) -> None:
        rec = self.last_recovery.get(team_id)
        if rec and 0 <= ev.game_seconds - rec[0] <= 15:
            self.stats[team_id].transitions.append(ev.game_seconds - rec[0])
            self.last_recovery.pop(team_id, None)

    def _shape(self, ev: MatchEvent) -> None:
        if not ev.positions or not self.possession_team:
            return
        poss = self.possession_team
        defending = self.other(poss)
        d_pts = [team_frame(defending, self.home, p.x, p.y) for p in ev.positions if p.team_id == defending]
        a_pts = [team_frame(poss, self.home, p.x, p.y) for p in ev.positions if p.team_id == poss]
        d_out = sorted(d_pts, key=lambda p: p[0])[1:]  # drop the goalkeeper (deepest)
        if len(d_out) >= 8:
            dst = self.stats[defending]
            dst.line_height_sum += sum(p[0] for p in d_out[:4]) / 4
            dst.line_height_n += 1
            xs, ys = [p[0] for p in d_out], [p[1] for p in d_out]
            dst.compact_sum += (max(xs) - min(xs)) * (max(ys) - min(ys))
            dst.compact_n += 1
        a_out = sorted(a_pts, key=lambda p: p[0])[1:]
        if len(a_out) >= 8:
            ast = self.stats[poss]
            ys = [p[1] for p in a_out]
            ast.width_sum += max(ys) - min(ys)
            ast.width_n += 1

    # ---------------------------------------------------------------- reads
    def window(self, seconds: int = 300, until: int | None = None) -> list[MatchEvent]:
        if not self.events:
            return []
        end = until if until is not None else self.events[-1].game_seconds
        out = []
        for ev in reversed(self.events):
            if ev.game_seconds < end - seconds:
                break
            if ev.game_seconds <= end:
                out.append(ev)
        return list(reversed(out))

    def window_stats(self, seconds: int = 300) -> dict:
        evs = self.window(seconds)
        res = {}
        for tid in (self.home, self.away):
            oid = self.other(tid)
            opp_passes = sum(1 for e in evs if e.type == E.PASS and e.team_id == oid
                             and (s := self.tf(e)) and s[0] <= 63)
            def_actions = [e for e in evs if e.team_id == tid and e.type in DEF_ACTIONS and (s := self.tf(e)) and s[0] >= 42]
            pressures = [e for e in evs if e.team_id == tid and e.type == E.PRESSURE]
            press_high = [e for e in pressures if (s := self.tf(e)) and s[0] >= 52.5]
            touches = sum(1 for e in evs if e.team_id == tid and e.type in (E.PASS, E.CARRY))
            ft = sum(1 for e in evs if e.team_id == tid and e.type == E.PASS and (s := self.tf(e)) and s[0] >= 70)
            shots = [e for e in evs if e.team_id == tid and e.type == E.SHOT]
            def_x = [self.tf(e)[0] for e in evs if e.team_id == tid and e.type in DEF_ACTIONS | {E.PRESSURE, E.RECOVERY} and self.tf(e)]
            res[tid] = {
                "ppda": round(opp_passes / len(def_actions), 2) if def_actions else None,
                "pressures": len(pressures),
                "pressures_opp_half": len(press_high),
                "touches": touches,
                "final_third_passes": ft,
                "shots": len(shots),
                "xg": round(sum(float(e.meta.get("xg", 0)) for e in shots), 2),
                "avg_defensive_action_x": round(sum(def_x) / len(def_x), 1) if def_x else None,
                "evidence": {"pressures": [e.event_id for e in press_high][-8:],
                             "def_actions": [e.event_id for e in def_actions][-8:]},
            }
        total_touch = sum(res[t]["touches"] for t in res) or 1
        total_ft = sum(res[t]["final_third_passes"] for t in res) or 1
        for t in res:
            res[t]["possession"] = round(res[t]["touches"] / total_touch, 3)
            res[t]["field_tilt"] = round(res[t]["final_third_passes"] / total_ft, 3)
        return res

    def line_height_window(self, team_id: str, seconds: int = 300) -> float | None:
        vals = []
        for ev in self.window(seconds):
            if not ev.positions:
                continue
            poss = self.possession_at(ev)
            if poss is None or poss == team_id:
                continue
            pts = sorted((team_frame(team_id, self.home, p.x, p.y) for p in ev.positions if p.team_id == team_id),
                         key=lambda p: p[0])[1:5]
            if len(pts) == 4:
                vals.append(sum(p[0] for p in pts) / 4)
        return round(sum(vals) / len(vals), 1) if vals else None

    def possession_at(self, ev: MatchEvent) -> str | None:
        if ev.type in (E.PASS, E.CARRY, E.SHOT, E.CORNER, E.KICK_OFF, E.RECOVERY, E.POSSESSION_CHANGE, E.OFFSIDE):
            return ev.team_id
        if ev.type in (E.PRESSURE, E.FOUL, E.CARD):
            return self.other(ev.team_id) if ev.team_id else None
        return ev.team_id

    def totals(self) -> dict:
        h, a = self.stats[self.home], self.stats[self.away]
        touches = (h.touches + a.touches) or 1
        ft = (h.final_third_passes + a.final_third_passes) or 1
        out = {}
        for tid, st in ((self.home, h), (self.away, a)):
            d = st.as_dict()
            d["possession"] = round(st.touches / touches, 3)
            d["field_tilt"] = round(st.final_third_passes / ft, 3)
            out[tid] = d
        return out

    def passing_network(self, team_id: str, top: int = 12) -> list[dict]:
        return [{"from": a, "to": b, "count": c} for (a, b), c in self.network[team_id].most_common(top)]

    def player_influence(self, team_id: str | None = None, top: int = 10) -> list[dict]:
        from app.data.teams import PLAYERS
        rows = []
        for pid, c in self.player.items():
            p = PLAYERS.get(pid)
            if not p or (team_id and p.team_id != team_id):
                continue
            score = (c["involvements"] * 0.15 + c["progressive_actions"] * 1.2 + c["xg_milli"] / 1000 * 8
                     + c["xa_milli"] / 1000 * 6 + c["goals"] * 4 + c["assists"] * 3 + c["recoveries"] * 0.6
                     + c["defensive_actions"] * 0.5 + c["pressures"] * 0.3)
            rows.append({"player_id": pid, "name": p.name, "team_id": p.team_id, "position": p.position,
                         "influence": round(score, 2), "goals": c["goals"], "assists": c["assists"],
                         "xg": round(c["xg_milli"] / 1000, 2), "xa": round(c["xa_milli"] / 1000, 2),
                         "progressive_actions": c["progressive_actions"], "recoveries": c["recoveries"],
                         "pressures": c["pressures"], "passes_completed": c["passes_completed"],
                         "defensive_actions": c["defensive_actions"]})
        return sorted(rows, key=lambda r: -r["influence"])[:top]

    def average_positions(self, last_n: int = 300) -> dict[str, list[float]]:
        sums: dict[str, list[float]] = {}
        for ev in self.events[-last_n:]:
            for p in ev.positions:
                acc = sums.setdefault(p.player_id, [0.0, 0.0, 0])
                acc[0] += p.x
                acc[1] += p.y
                acc[2] += 1
        return {pid: [round(a[0] / a[2], 1), round(a[1] / a[2], 1)] for pid, a in sums.items() if a[2]}

    def snapshot(self) -> dict:
        last = self.events[-1] if self.events else None
        return {
            "match_id": self.match_id,
            "minute": last.minute if last else 0,
            "second": last.second if last else 0,
            "score": dict(self.score),
            "totals": self.totals(),
            "window": self.window_stats(300),
            "momentum": self.momentum_index(),
            "momentum_raw": {k: round(v, 3) for k, v in self.momentum.items()},
            "substitutions": list(self.substitutions),
            "possession_team": self.possession_team,
        }
