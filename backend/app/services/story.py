"""AI Match Story: 5 Moments That Changed the Match, How It Was Won, Player of the Match, Tactical Battle,
Biggest Missed Opportunity.

Facts are selected deterministically (insights, pattern history, influence model, shot xG); the large
model only writes prose over them, and the prose is verified like any other insight.
"""
from __future__ import annotations

import json

from app.agents.evidence import verify_output
from app.data.teams import player_name, team_name
from app.models.domain import EventType

STORY_PROMPT = """You are the storytelling agent of Football Intelligence OS. Using ONLY the FACTS JSON, write the match story.
Never add numbers, players or events that are not in FACTS.
Goal times, scorers and the order of goals must come ONLY from FACTS.goals — never use the current clock as a goal time.
If FACTS.result_note is set (e.g. a penalty shoot-out), the winner is decided by it — say so explicitly.
If FACTS.status is "in_progress", this is the story SO FAR: never say the match ended, was won, drawn or lost — say who
leads or that it is level at FACTS.current_clock_not_a_goal_time, and title "how_won" content as how the game has unfolded. Output JSON:
{"headline": "≤ 10 words",
 "how_won": "3–4 sentences: how the match was won, cause → effect",
 "moments": [{"moment_id": "<from FACTS>", "title": "≤ 6 words", "why_it_mattered": "1 sentence"}],
 "potm_explanation": "2 sentences on why FACTS.player_of_the_match earned it",
 "tactical_battle": "2–3 sentences on how the tactical patterns traded blows",
 "missed_opportunity": "1–2 sentences on FACTS.biggest_missed_opportunity"}"""


def valid_minutes(f: dict) -> set[int]:
    vm = {int(g["clock"].split(":")[0]) for g in f["goals"]} | {m["minute"] for m in f["moments"]} | \
         {p["minute"] for p in f["tactical_patterns"]} | {s_["minute"] for s_ in f["substitutions"]}
    if f.get("biggest_missed_opportunity"):
        vm.add(int(f["biggest_missed_opportunity"]["clock"].split(":")[0]))
    return vm


def bad_minutes(text: str, valid: set[int]) -> list[int]:
    """Minutes cited in prose ("87'", "minute 87", "87th minute") that are not real event minutes."""
    import re as _re
    cited = [int(x) for x in _re.findall(r"(?:minute\s+|\b)(\d{1,3})(?:'|th minute|st minute|nd minute|rd minute|\s*min\b)", text or "")]
    cited += [int(x) for x in _re.findall(r"minute\s+(\d{1,3})", text or "")]
    return [m for m in cited if valid and min(abs(m - v) for v in valid) > 1]


class StoryService:
    def __init__(self, llm) -> None:
        self.llm = llm

    def facts(self, rt) -> dict:
        eng = rt.engine
        cands = []
        for i in rt.insights:
            story = (i.statistics or {}).get("story", {})
            w = story.get("story_weight", i.significance)
            if i.category in ("GOAL", "TURNING_POINT", "TACTICAL_SHIFT", "HIGH_PRESS", "MOMENTUM_SHIFT", "DANGEROUS_ATTACK") or story.get("turning_point"):
                cands.append((w + (0.3 if i.category == "GOAL" else 0), i))
        cands.sort(key=lambda x: -x[0])
        moments, used = [], []
        for w, i in cands:
            if any(abs(i.minute - m) < 4 for m in used):
                continue
            used.append(i.minute)
            moments.append({"moment_id": i.insight_id, "minute": i.minute, "clock": f"{i.minute:02d}:{i.second:02d}",
                            "category": i.category, "headline": i.headline, "summary": i.explanations.get("intermediate", "")[:300],
                            "event_id": i.event_id, "weight": round(w, 2)})
            if len(moments) == 5:
                break
        moments.sort(key=lambda m: (m["minute"], m["clock"]))
        infl = eng.player_influence(top=3)
        shots = [e for e in eng.events if e.type == EventType.SHOT and e.outcome != "goal"]
        miss = max(shots, key=lambda e: e.meta.get("xg", 0), default=None)
        h, a = eng.home, eng.away
        winner = h if eng.score[h] > eng.score[a] else a if eng.score[a] > eng.score[h] else None
        pens = rt.match.notes.get("penalties") if any(e.type == EventType.FULL_TIME for e in eng.events[-3:]) else None
        if pens and winner is None:
            winner = next((t for t in (h, a) if team_name(t) in pens), None)
        finished = any(e.type == EventType.FULL_TIME for e in eng.events[-3:])
        return {
            "status": "full_time" if finished else "in_progress",
            "result_note": rt.match.notes.get("penalties") if finished else None,
            "data_source": rt.match.notes.get("attribution", "synthetic demo data"),
            "score": f"{team_name(h)} {eng.score[h]}–{eng.score[a]} {team_name(a)}",
            "current_clock_not_a_goal_time": eng.events[-1].clock if eng.events else "00:00",
            "winner": (team_name(winner) if winner else None) if finished else None,
            "leader": team_name(winner) if winner else None,
            "moments": moments,
            "goals": [{"clock": e.clock, "team": team_name(e.team_id), "scorer": player_name(e.player_id),
                       "assist": player_name(e.related_player_id) if e.related_player_id else None, "xg": e.meta.get("xg"),
                       "event_id": e.event_id} for e in eng.events if e.type == EventType.GOAL],
            "player_of_the_match": infl[0] if infl else None,
            "runners_up": infl[1:],
            "tactical_patterns": [{"minute": p["minute"], "type": p["type"], "team": team_name(p["team_id"]), "summary": p["summary"]}
                                  for p in rt.patterns.history if p["event"] == "start"],
            "substitutions": [{"minute": s["minute"], "team": team_name(s["team_id"]), "on": player_name(s["on"]),
                               "off": player_name(s["off"]), "reason": s["reason"]} for s in eng.substitutions],
            "biggest_missed_opportunity": {"clock": miss.clock, "team": team_name(miss.team_id), "player": player_name(miss.player_id),
                                           "xg": miss.meta.get("xg"), "outcome": miss.outcome, "event_id": miss.event_id} if miss else None,
            "totals": {team_name(t): {k: v for k, v in d.items() if k in ("possession", "xg", "shots", "ppda", "field_tilt", "high_turnovers")}
                       for t, d in eng.totals().items()},
        }

    def fallback(self, f: dict) -> dict:
        goals = "; ".join(f"{g['clock']} {g['scorer']} ({g['team']})" for g in f["goals"]) or "no goals"
        potm = f["player_of_the_match"]
        miss = f["biggest_missed_opportunity"]
        pats = f["tactical_patterns"]
        return {
            "headline": f"{f['score']}" + (f" — {f['winner']} win it" if f["winner"] else
                                            (f" after {f['current_clock_not_a_goal_time']}" if f["status"] == "in_progress" else "")),
            "how_won": f"Goals: {goals}. " + (" ".join(f"{p['minute']}': {p['summary']}" for p in pats[:3])),
            "moments": [{"moment_id": m["moment_id"], "title": m["headline"][:40], "why_it_mattered": m["summary"][:160]} for m in f["moments"]],
            "potm_explanation": (f"{potm['name']} topped the influence model with {potm['progressive_actions']} progressive actions, "
                                 f"{potm['goals']} goals and {potm['assists']} assists.") if potm else "",
            "tactical_battle": " ".join(f"{p['minute']}': {p['team']} — {p['type'].replace('_', ' ').lower()}." for p in pats[:5]),
            "missed_opportunity": (f"{miss['player']} ({miss['team']}) at {miss['clock']}: a {miss['xg']} xG chance, {miss['outcome'].replace('_', ' ')}."
                                   if miss else ""),
        }

    async def build(self, rt, tier: str = "large") -> dict:
        f = self.facts(rt)
        res = await self.llm.complete_json(system=STORY_PROMPT, user="FACTS:\n" + json.dumps(f, default=str)[:12000],
                                           tier=tier, fallback=lambda: self.fallback(f), max_tokens=1100,
                                           interactive=True)
        story = res.data
        check = verify_output({"explanations": {"how_won": story.get("how_won", ""), "potm": story.get("potm_explanation", ""),
                                                "battle": story.get("tactical_battle", ""), "miss": story.get("missed_opportunity", "")},
                               "headline": story.get("headline", "")}, {"facts": f, "valid_event_ids": []})
        if not check["passed"] and not res.fallback:
            safe = self.fallback(f)
            fields = {"how_won": "how_won", "potm": "potm_explanation", "battle": "tactical_battle", "miss": "missed_opportunity",
                      "headline": "headline"}
            for issue in check["issues"]:
                k = fields.get(issue.split(":")[0])
                if k:
                    story[k] = safe[k]
        # semantic guard: every minute the prose mentions must be a real event minute from FACTS
        import re as _re
        valid_min = {int(g["clock"].split(":")[0]) for g in f["goals"]} | {m["minute"] for m in f["moments"]} | \
                    {p["minute"] for p in f["tactical_patterns"]} | {s_["minute"] for s_ in f["substitutions"]}
        if f.get("biggest_missed_opportunity"):
            valid_min.add(int(f["biggest_missed_opportunity"]["clock"].split(":")[0]))
        safe = self.fallback(f)
        for key in ("how_won", "potm_explanation", "tactical_battle", "missed_opportunity", "headline"):
            txt = story.get(key) or ""
            cited = [int(x) for x in _re.findall(r"(?:minute\s+|\b)(\d{1,3})(?:'|th minute|st minute|nd minute|rd minute|\s*min\b)", txt)]
            cited += [int(x) for x in _re.findall(r"minute\s+(\d{1,3})", txt)]
            if any(abs(m - v) > 1 for m in cited for v in [min(valid_min, key=lambda v: abs(v - m))] if valid_min):
                story[key] = safe[key]
                check.setdefault("issues", []).append(f"{key}: cited a minute that is not an event minute → replaced")
        by_id = {m["moment_id"]: m for m in f["moments"]}
        moments = []
        for m in story.get("moments", []):
            base = by_id.get(m.get("moment_id"))
            if base:
                moments.append({**base, "title": m.get("title") or base["headline"], "why_it_mattered": m.get("why_it_mattered", "")})
        if len(moments) < len(f["moments"]):
            have = {m["moment_id"] for m in moments}
            moments += [{**m, "title": m["headline"], "why_it_mattered": m["summary"][:160]} for m in f["moments"] if m["moment_id"] not in have]
        moments.sort(key=lambda m: m["clock"])
        return {**story, "moments": moments, "facts": f, "model": res.model, "verification": check}
