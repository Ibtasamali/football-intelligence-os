"""Team intelligence."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import container
from app.data.teams import PLAYERS, TEAMS

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/{team_id}")
async def get_team(team_id: str, match_id: str | None = None, c=Depends(container)):
    t = TEAMS.get(team_id)
    if not t:
        raise HTTPException(404, "team not found")
    out = {"team": t.model_dump(), "squad": [p.model_dump() for p in PLAYERS.values() if p.team_id == team_id]}
    rt = c.runtimes.get(match_id) if match_id else None
    if rt:
        out["match"] = rt.engine.totals()[team_id]
        out["network"] = rt.engine.passing_network(team_id, 15)
        out["patterns"] = [p for p in rt.patterns.history if p["team_id"] == team_id]
    out["memories"] = await c.memory.recall(t.name, entities=[team_id], k=4)
    out["history"] = await c.db.find("historical_matches", {"teams": team_id}, projection={"_id": 0, "embedding": 0})
    return out
