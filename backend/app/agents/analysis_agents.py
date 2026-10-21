"""Perception, tactical and entity agents — deterministic, zero-token, evidence-producing."""
from __future__ import annotations

from app.agents.base import Agent, AgentContext
from app.data.teams import PLAYERS, TEAMS, player_name, team_name
from app.models.domain import EventType
from app.prediction.models import substitution_impact
from app.tactical.engine import channel, team_frame
from app.tactical.patterns import ZONES

E = EventType


# ============================================================== perception
class MatchIntelligenceAgent(Agent):
    name, family = "match_intelligence", "perception"
    description = "Game state: score, clock, phase, who needs what."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        h, a = eng.home, eng.away
        score = (ctx.state.get("frozen") or {}).get("score") or eng.score
        minute = ctx.event.minute if ctx.event else (eng.events[-1].minute if eng.events else 0)
        diff = score[h] - score[a]
        state = "level" if diff == 0 else (f"{team_name(h)} lead" if diff > 0 else f"{team_name(a)} lead")
        phase = "opening" if minute < 15 else "first half" if minute < 45 else "second half" if minute < 75 else "closing stages"
        return ({"minute": minute, "score": dict(score), "game_state": state, "phase": phase,
                 "score_text": f"{team_name(h)} {score[h]}–{score[a]} {team_name(a)}",
                 "late_and_close": minute >= 75 and abs(diff) <= 1}, 1.0, [])


class EventInterpretationAgent(Agent):
    name, family = "event_interpretation", "perception"
    description = "Turns a raw event into football meaning (zone, threat, type of action)."

    async def execute(self, ctx: AgentContext):
        ev = ctx.event
        if ev is None:
            return {"label": "no event"}, 0.5, []
        eng = ctx.runtime.engine
        p = eng.tf(ev)
        zone = None
        if p:
            zone = ("final third" if p[0] >= 70 else "middle third" if p[0] >= 35 else "defensive third")
            zone += f", {channel(p[1])} channel"
        who = player_name(ev.player_id)
        team = team_name(ev.team_id)
        t = ev.type
        delta = ctx.state.get("event_delta", {})
        label = {E.GOAL: "Goal", E.SHOT: "Shot", E.SAVE: "Save", E.SUBSTITUTION: "Substitution", E.CARD: "Card",
                 E.CORNER: "Corner", E.FOUL: "Foul", E.OFFSIDE: "Offside"}.get(t, t.value.replace("_", " ").title())
        details = []
        if t == E.SHOT:
            details.append(f"xG {ev.meta.get('xg')}" + (" (header)" if ev.meta.get("header") else ""))
            details.append(ev.outcome.replace("_", " ") if ev.outcome else "")
        if t == E.GOAL:
            details.append(f"assist {player_name(ev.related_player_id)}" if ev.related_player_id else "unassisted")
            details.append(f"xG {ev.meta.get('xg')}")
        if t == E.RECOVERY and delta.get("high_turnover"):
            label = "High turnover"
            details.append("ball won within 40 m of the opponent goal")
        if t == E.SUBSTITUTION:
            details.append(f"{who} on for {player_name(ev.related_player_id)}")
            if ev.meta.get("reason"):
                details.append(ev.meta["reason"])
        if t == E.CARD:
            details.append(f"{ev.outcome} card")
        if delta.get("progressive"):
            details.append("progressive")
        if delta.get("final_third_entry"):
            details.append("final-third entry")
        desc = f"{label} — {who} ({team})" + (f" in the {zone}" if zone else "")
        if any(details):
            desc += ": " + ", ".join(d for d in details if d)
        return {"label": label, "description": desc, "zone": zone, "player": who, "team": team,
                "clock": ev.clock, "event_id": ev.event_id}, 0.95, [ev.event_id]


class FormationAgent(Agent):
    name, family = "formation", "perception"
    description = "Infers each team's live shape from the 22-player snapshot (line clustering)."

    @staticmethod
    def infer(positions, team_id: str, home_id: str) -> str:
        pts = sorted(team_frame(team_id, home_id, p.x, p.y)[0] for p in positions if p.team_id == team_id)[1:]
        if len(pts) < 9:
            return "unknown"
        lines, cur = [], [pts[0]]
        for x in pts[1:]:
            if x - cur[-1] > 6.5:
                lines.append(cur)
                cur = [x]
            else:
                cur.append(x)
        lines.append(cur)
        while len(lines) > 4:  # merge the closest adjacent lines
            gaps = [lines[i + 1][0] - lines[i][-1] for i in range(len(lines) - 1)]
            i = gaps.index(min(gaps))
            lines[i] = lines[i] + lines.pop(i + 1)
        return "-".join(str(len(l)) for l in lines)

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        ev = next((e for e in reversed(eng.events) if e.positions), None)
        if not ev:
            return {}, 0.3, []
        poss = eng.possession_at(ev)
        out = {}
        for tid in (eng.home, eng.away):
            out[tid] = {"nominal": TEAMS[tid].formation, "live": self.infer(ev.positions, tid, eng.home),
                        "phase": "in possession" if poss == tid else "out of possession"}
        return {"shapes": out, "snapshot_event": ev.event_id}, 0.7, [ev.event_id]


class MomentumAgent(Agent):
    name, family = "momentum", "perception"
    description = "Exponentially-decayed threat momentum, trend and shifts."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        idx = eng.momentum_index()
        hist = list(eng.momentum_history)
        now = hist[-1][0] if hist else 0
        past = next((m for t, m in hist if t >= now - 180), idx)
        trend = round(idx - past, 3)
        leader = eng.home if idx > 0.1 else eng.away if idx < -0.1 else None
        shift = abs(trend) >= 0.35
        return {"index": idx, "trend_3min": trend, "leader": leader,
                "leader_name": team_name(leader) if leader else "neither side",
                "shift": shift, "toward": (eng.home if trend > 0 else eng.away) if shift else None,
                "series": [round(m, 3) for _, m in hist[-120:]]}, 0.8, []


class GoalProbabilityAgent(Agent):
    name, family = "goal_probability", "perception"
    description = "Shot quality (xG), cumulative xG and chance conversion context."

    async def execute(self, ctx: AgentContext):
        eng, ev = ctx.runtime.engine, ctx.event
        tot = eng.totals()
        shot = ev if ev and ev.type in (E.SHOT, E.GOAL) else None
        out = {"xg_totals": {t: tot[t]["xg"] for t in tot}, "shots": {t: tot[t]["shots"] for t in tot}}
        evidence = []
        if shot:
            xg = shot.meta.get("xg")
            out["shot_xg"] = xg
            out["shot_quality"] = ("big chance" if (xg or 0) >= 0.3 else "decent chance" if (xg or 0) >= 0.1 else "low-quality attempt")
            out["conversion_note"] = (f"A {xg} xG chance is scored roughly {round((xg or 0) * 10)} times in 10."
                                      if xg is not None else "")
            evidence.append(shot.event_id)
        return out, 0.85, evidence


# ============================================================== tactical
class TacticalAnalysisAgent(Agent):
    name, family = "tactical_analysis", "tactical"
    description = "Selects the primary tactical story from active and newly-detected patterns."

    async def execute(self, ctx: AgentContext):
        new = ctx.state.get("new_patterns", [])
        active = ctx.runtime.patterns.active_list()
        primary = new[0] if new else (max(active, key=lambda p: p["confidence"]) if active else None)
        evidence = primary["evidence_event_ids"] if primary else []
        return {"primary_pattern": primary, "active_patterns": active, "new_patterns": new,
                "summary": primary["summary"] if primary else "No dominant tactical pattern right now."}, \
            (primary["confidence"] if primary else 0.4), evidence


class DefensiveAnalysisAgent(Agent):
    name, family = "defensive_analysis", "tactical"
    description = "Line height, compactness, PPDA and defensive actions of the defending team."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        ev = ctx.event
        defending = eng.other(ev.team_id) if ev and ev.team_id in eng.stats else eng.away
        tot = eng.totals()[defending]
        w = eng.window_stats(300)[defending]
        return {"team_id": defending, "team": team_name(defending),
                "line_height_5min": eng.line_height_window(defending, 300),
                "line_height_match": tot["defensive_line_height"], "compactness_m2": tot["compactness_m2"],
                "ppda_5min": w["ppda"], "ppda_match": tot["ppda"], "defensive_actions": tot["defensive_actions"]}, \
            0.8, w["evidence"]["def_actions"][-5:]


class AttackingAnalysisAgent(Agent):
    name, family = "attacking_analysis", "tactical"
    description = "Field tilt, progression, final-third entries and width of the attacking team."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        ev = ctx.event
        tid = ev.team_id if ev and ev.team_id in eng.stats else eng.home
        tot = eng.totals()[tid]
        w = eng.window_stats(300)[tid]
        recent = [e for e in eng.window(300) if e.team_id == tid and e.type in (E.PASS, E.CARRY) and e.outcome == "success"]
        chans = {"left": 0, "centre": 0, "right": 0}
        for e in recent:
            end = eng.tf(e, end=True)
            if end and end[0] >= 52.5:
                chans[channel(end[1])] += 1
        return {"team_id": tid, "team": team_name(tid), "field_tilt_5min": w["field_tilt"],
                "field_tilt_match": tot["field_tilt"], "progressive_passes": tot["progressive_passes"],
                "final_third_entries": tot["final_third_entries"], "attacking_width_m": tot["attacking_width"],
                "channels_5min": chans, "xg_5min": w["xg"]}, 0.8, [e.event_id for e in recent[-5:]]


class PassingNetworkAgent(Agent):
    name, family = "passing_network", "tactical"
    description = "Most frequent connections and the hub player (weighted degree)."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        ev = ctx.event
        tid = ev.team_id if ev and ev.team_id in eng.stats else eng.home
        net = eng.passing_network(tid, 12)
        degree: dict[str, int] = {}
        for n in net:
            degree[n["from"]] = degree.get(n["from"], 0) + n["count"]
            degree[n["to"]] = degree.get(n["to"], 0) + n["count"]
        hub = max(degree, key=degree.get) if degree else None
        return {"team_id": tid, "edges": [{**n, "from_name": player_name(n["from"]), "to_name": player_name(n["to"])} for n in net],
                "hub": hub, "hub_name": player_name(hub) if hub else None,
                "top_connection": f"{player_name(net[0]['from'])} → {player_name(net[0]['to'])} ({net[0]['count']} passes)" if net else None}, 0.75, []


class SpaceAnalysisAgent(Agent):
    name, family = "space_analysis", "tactical"
    description = "Numerical situations per channel and space between/behind lines from the latest snapshot."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        ev = next((e for e in reversed(eng.events) if e.positions), None)
        if not ev:
            return {}, 0.3, []
        att = eng.possession_at(ev) or eng.home
        dfd = eng.other(att)
        counts = {}
        for ch, (y0, y1) in {"right": (0, 22.7), "centre": (22.7, 45.3), "left": (45.3, 68)}.items():
            a = d = 0
            for p in ev.positions:
                fx, fy = team_frame(att, eng.home, p.x, p.y)
                if fx >= 52.5 and y0 <= fy < y1:
                    if p.team_id == att:
                        a += 1
                    else:
                        d += 1
            counts[ch] = {"attackers": a, "defenders": d, "situation": f"{a}v{d}"}
        overload = max(counts, key=lambda c: counts[c]["attackers"] - counts[c]["defenders"])
        dpts = sorted(team_frame(dfd, eng.home, p.x, p.y)[0] for p in ev.positions if p.team_id == dfd)[1:]
        line = sum(dpts[:4]) / 4 if len(dpts) >= 4 else None
        mid = sum(dpts[4:7]) / 3 if len(dpts) >= 7 else None
        out = {"attacking_team": att, "channels": counts, "best_overload": overload,
               "best_overload_situation": counts[overload]["situation"],
               "defending_line_m": round(line, 1) if line else None,
               "space_behind_line_m": round(line, 1) if line else None,
               "gap_between_lines_m": round(mid - line, 1) if line and mid else None, "snapshot_event": ev.event_id}
        return out, 0.7, [ev.event_id]


class PressingAnalysisAgent(Agent):
    name, family = "pressing_analysis", "tactical"
    description = "Pressing intensity (PPDA), pressure volume and pressing success (turnover within 6 s)."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        out = {}
        evidence = []
        win = eng.window(600)
        for tid in (eng.home, eng.away):
            press = [e for e in win if e.team_id == tid and e.type == E.PRESSURE]
            success = 0
            for p in press:
                for f in win:
                    if f.game_seconds < p.game_seconds:
                        continue
                    if f.game_seconds - p.game_seconds > 6:
                        break
                    if f.team_id == tid and f.type == E.RECOVERY:
                        success += 1
                        evidence += [p.event_id, f.event_id]
                        break
            w = eng.window_stats(300)[tid]
            out[tid] = {"ppda_5min": w["ppda"], "ppda_match": eng.totals()[tid]["ppda"], "pressures_10min": len(press),
                        "press_success_rate": round(success / len(press), 2) if press else None,
                        "high_turnovers_match": eng.totals()[tid]["high_turnovers"]}
        return out, 0.8, evidence[-8:]


class SubstitutionImpactAgent(Agent):
    name, family = "substitution_impact", "tactical"
    description = "Before/after comparison of output in equal windows around each substitution."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        rows = []
        for s in eng.substitutions[-4:]:
            imp = substitution_impact(eng, s)
            rows.append({**s, "on_name": player_name(s["on"]), "off_name": player_name(s["off"]),
                         "impact": imp, "status": "measured" if imp else "too early to measure"})
        return {"substitutions": rows}, 0.7, [s["event_id"] for s in eng.substitutions[-4:]]


# ============================================================== entities
class PlayerIntelligenceAgent(Agent):
    name, family = "player_intelligence", "entity"
    description = "Match profile of involved players: role, involvement, influence rank."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        ids = list(dict.fromkeys([pid for pid in ctx.state.get("player_ids", []) if pid]))[:3]
        if ctx.event and ctx.event.player_id and ctx.event.player_id not in ids:
            ids.insert(0, ctx.event.player_id)
        ranking = eng.player_influence(top=40)
        rank = {r["player_id"]: (i + 1, r) for i, r in enumerate(ranking)}
        players = []
        for pid in ids[:3]:
            p = PLAYERS.get(pid)
            if not p:
                continue
            r = rank.get(pid, (None, {}))
            players.append({"player_id": pid, "name": p.name, "position": p.position, "role": p.role,
                            "team": team_name(p.team_id), "influence_rank": r[0], "stats": r[1]})
        return {"players": players, "top_influence": ranking[:3]}, 0.8, []


class TeamIntelligenceAgent(Agent):
    name, family = "team_intelligence", "entity"
    description = "Side-by-side team profile from match totals."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        tot = eng.totals()
        keys = ["possession", "field_tilt", "xg", "shots", "ppda", "progressive_passes", "high_turnovers", "pass_completion"]
        return {"teams": {tid: {"name": team_name(tid), "style": TEAMS[tid].style, **{k: tot[tid][k] for k in keys}}
                          for tid in tot}}, 0.9, []
