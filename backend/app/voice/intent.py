"""Intent detection for spoken / typed fan questions.

Rule-based first (zero tokens, <1 ms). Only ambiguous questions fall through to the small model
in the query graph. Also extracts entities (teams, players) mentioned by name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.data.teams import PLAYERS, TEAMS

RULES: list[tuple[str, list[str]]] = [
    ("EXPLAIN_SIMPLER", [r"\bbeginner\b", r"\bsimple\b", r"\bsimpl", r"like i'?m (five|5|a kid|new)", r"\bkid", r"\beasier\b", r"\bplain english\b"]),
    ("EXPLAIN_EXPERT", [r"\banalyst\b", r"\bexpert\b", r"\bpro(fessional)?\b", r"\bin depth\b", r"\btechnical\b", r"\bdeeper\b"]),
    ("COMPARE", [r"\bcompare\b", r"\bversus\b", r"\bvs\.?\b", r"\bdifference\b", r"\bprevious attack\b"]),
    ("SIMILAR", [r"\bsimilar\b", r"\bremind", r"\blike (the|that|last)\b", r"\bseen this before\b", r"\bhistor"]),
    ("BEST_PLAYER", [r"\bbest player\b", r"\bplayer of the match\b", r"\bmotm\b", r"\bwho('?s| is) (playing )?(best|standing out)", r"\bstar\b"]),
    ("PREDICT", [r"\bwhat (will|might|could) happen\b", r"\bnext\b", r"\bpredict", r"\blikely\b", r"\bgoing to score\b"]),
    ("STORY", [r"\bsummar", r"\bstory\b", r"\bhow (was|did) .* (won|win)\b", r"\bturning point", r"\bkey moments\b"]),
    ("WHY", [r"^why\b", r"\bwhy did\b", r"\bwhy was\b", r"\bhow did that\b", r"\bwhat caused\b", r"\breason\b"]),
    ("MOMENTUM", [r"\bmomentum\b", r"\bon top\b", r"\bdominat", r"\bin control\b"]),
    ("STATS", [r"\bstats?\b", r"\bpossession\b", r"\bxg\b", r"\bshots?\b", r"\bppda\b", r"\bpass(es|ing)? (completion|accuracy)\b"]),
    ("TACTICS", [r"\btactic", r"\bformation\b", r"\bpress", r"\bshape\b", r"\bblock\b", r"\boverload\b"]),
    ("WHAT_HAPPENED", [r"\bwhat (just )?happened\b", r"\bwhat'?s going on\b", r"\bupdate\b", r"\bscore\b", r"\bjust now\b"]),
]


@dataclass
class Intent:
    name: str
    confidence: float
    teams: list[str] = field(default_factory=list)
    players: list[str] = field(default_factory=list)
    style_override: str | None = None


def detect_intent(text: str, team_ids: list[str] | None = None) -> Intent:
    t = text.lower().strip()
    name, conf = "GENERAL", 0.4
    for intent, pats in RULES:
        if any(re.search(p, t) for p in pats):
            name, conf = intent, 0.9
            break
    teams = [tid for tid, team in TEAMS.items() if (not team_ids or tid in team_ids) and
             ( team.name.lower() in t or team.short_name.lower() in t.split() or team.name.split()[0].lower() in t)]
    players = [pid for pid, p in PLAYERS.items() if (not team_ids or p.team_id in team_ids)
               and (p.name.lower() in t or p.name.split()[-1].lower() in re.findall(r"[a-zà-ÿ]+", t))]
    style = "beginner" if name == "EXPLAIN_SIMPLER" else "professional" if name == "EXPLAIN_EXPERT" else None
    return Intent(name, conf, teams, players, style)
