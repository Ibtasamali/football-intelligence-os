"""CAG — Context-Augmented Generation.

A versioned, TTL'd snapshot of everything an agent needs about the *live* match: score, shape, last 20
events, last-5-minute metrics, momentum, active patterns, substitutions and player states. Agents read
this instead of re-querying MongoDB or re-running retrieval for every question.
"""
from __future__ import annotations

import time

from app.data.teams import PLAYERS, TEAMS, player_name, team_name


def compact_event(ev) -> dict:
    return {"event_id": ev.event_id, "seq": ev.seq, "clock": ev.clock, "type": ev.type.value, "team": ev.team_id,
            "player": player_name(ev.player_id) if ev.player_id else None, "player_id": ev.player_id,
            "outcome": ev.outcome, "x": ev.x, "y": ev.y, "end_x": ev.end_x, "end_y": ev.end_y,
            "xg": ev.meta.get("xg"),
            **{k: True for k in ("penalty", "header", "own_goal", "cross", "big_chance") if ev.meta.get(k)},
            **({"set_piece": ev.meta["set_piece"]} if ev.meta.get("set_piece") else {})}


class ContextCache:
    def __init__(self, kv, ttl: int) -> None:
        self.kv, self.ttl = kv, ttl  # JsonKV
        self.hits = self.misses = 0

    @staticmethod
    def key(match_id: str) -> str:
        return f"cag:ctx:{match_id}"

    async def refresh(self, runtime, full: bool = True) -> dict:
        eng = runtime.engine
        prev = await self.kv.get_json(self.key(runtime.match_id)) or {}
        ctx = {
            "match_id": runtime.match_id,
            "version": prev.get("version", 0) + 1,
            "updated_at": time.time(),
            "ttl": self.ttl,
            "clock": eng.events[-1].clock if eng.events else "00:00",
            "minute": eng.events[-1].minute if eng.events else 0,
            "score": dict(eng.score),
            "score_text": f"{team_name(eng.home)} {eng.score[eng.home]}–{eng.score[eng.away]} {team_name(eng.away)}",
            "formations": runtime.formations(),
            "last_events": [compact_event(e) for e in eng.events[-20:]],
            "momentum": eng.momentum_index(),
            "active_patterns": runtime.patterns.active_list(),
            "substitutions": eng.substitutions,
            "possession_team": eng.possession_team,
        }
        if full or "last_5_min" not in prev:
            ctx["last_5_min"] = {t: {k: v for k, v in d.items() if k != "evidence"} for t, d in eng.window_stats(300).items()}
            ctx["totals"] = eng.totals()
            ctx["player_states"] = eng.player_influence(top=8)
        else:
            for k in ("last_5_min", "totals", "player_states"):
                ctx[k] = prev.get(k)
        await self.kv.set_json(self.key(runtime.match_id), ctx, self.ttl)
        return ctx

    async def get(self, match_id: str) -> dict | None:
        ctx = await self.kv.get_json(self.key(match_id))
        if ctx:
            self.hits += 1
        else:
            self.misses += 1
        return ctx

    @staticmethod
    def sufficient_for(intent: str, ctx: dict | None) -> bool:
        """Can live context alone answer this intent? (Avoids retrieval when it can.)"""
        if not ctx:
            return False
        return intent in {"WHAT_HAPPENED", "SCORE", "STATS", "BEST_PLAYER", "PREDICT", "MOMENTUM",
                          "EXPLAIN_SIMPLER", "EXPLAIN_EXPERT", "WHY"}


def team_meta(team_ids: list[str] | None = None) -> dict:
    return {tid: {"name": t.name, "short": t.short_name, "colors": t.colors, "formation": t.formation, "coach": t.coach,
                  "style": t.style} for tid, t in TEAMS.items() if not team_ids or tid in team_ids}


def roster(team_ids: list[str] | None = None) -> list[dict]:
    return [p.model_dump() for p in PLAYERS.values() if not team_ids or p.team_id in team_ids]
