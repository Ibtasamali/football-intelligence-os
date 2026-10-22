"""Per-match runtime: tactical engine, pattern tracker, insights and per-user conversational focus."""
from __future__ import annotations

import uuid

from app.agents.analysis_agents import FormationAgent
from app.models.domain import Insight, Match
from app.tactical.engine import TacticalEngine
from app.tactical.patterns import PatternTracker


class MatchRuntime:
    def __init__(self, match: Match) -> None:
        self.match = match
        self.match_id = match.match_id
        self.engine = TacticalEngine(match.match_id, match.home_team_id, match.away_team_id)
        self.patterns = PatternTracker("synthetic")
        self.insights: list[Insight] = []
        self.answers: dict[str, Insight] = {}
        self.last_deep_t = -999
        self.events_since_refresh = 0
        self.session = uuid.uuid4().hex[:10]
        self.jump_points: list[dict] = []
        self.archive_status: dict | None = None
        self.archive_task = None  # answer-cache namespace; changes on every reset

    def formations(self) -> dict:
        ev = next((e for e in reversed(self.engine.events[-30:]) if e.positions), None)
        if not ev:
            return {}
        return {tid: FormationAgent.infer(ev.positions, tid, self.engine.home) for tid in (self.engine.home, self.engine.away)}

    def position_of(self, player_id: str) -> list[float] | None:
        for ev in reversed(self.engine.events[-5:]):
            for p in ev.positions:
                if p.player_id == player_id:
                    return [p.x, p.y]
        return None

    def latest_focus(self) -> Insight | None:
        ordered = sorted((i for i in self.insights if i.category != "ANSWER"), key=lambda i: (i.minute, i.second))
        strong = [i for i in ordered if i.significance >= 0.5]
        return (strong or ordered[-1:] or [None])[-1]

    def last_focus_for(self, user_id: str | None) -> Insight | None:
        return self.answers.get(user_id or "") or self.latest_focus()

    def find_focus(self, question: str, teams: list[str], user_id: str | None) -> Insight | None:
        q = question.lower()
        if any(w in q for w in ("goal", "score", "scored", "equalis", "equaliz", "level", "winner", "lead", "comeback")):
            goals = sorted((i for i in self.insights if i.category == "GOAL" and (not teams or i.team_id in teams)),
                           key=lambda i: (i.minute, i.second))
            if goals:
                return goals[-1]
        if any(w in q for w in ("press", "overload", "block", "counter", "transition")):
            pats = sorted((i for i in self.insights if i.patterns and (not teams or i.team_id in teams)),
                          key=lambda i: (i.minute, i.second))
            if pats:
                return pats[-1]
        return self.last_focus_for(user_id)

    def remember_answer(self, user_id: str | None, insight: Insight) -> None:
        if user_id:
            self.answers[user_id] = insight
