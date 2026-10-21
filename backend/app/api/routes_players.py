"""Player intelligence."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import container
from app.data.teams import PLAYERS

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("")
async def list_players():
    return {"players": [p.model_dump() for p in PLAYERS.values()]}


@router.get("/{player_id}")
async def get_player(player_id: str, match_id: str | None = None, c=Depends(container)):
    p = PLAYERS.get(player_id)
    if not p:
        raise HTTPException(404, "player not found")
    out = {"player": p.model_dump()}
    rt = c.runtimes.get(match_id) if match_id else None
    if rt:
        ranking = rt.engine.player_influence(top=40)
        for i, r in enumerate(ranking):
            if r["player_id"] == player_id:
                out["match"] = {**r, "influence_rank": i + 1}
        out["connections"] = [n for n in rt.engine.passing_network(p.team_id, 40) if player_id in (n["from"], n["to"])][:8]
        out["recent_insights"] = [{"insight_id": i.insight_id, "minute": i.minute, "headline": i.headline}
                                  for i in rt.insights if player_id in i.player_ids][-6:]
        heat = [[e.x, e.y] for e in rt.engine.events if e.player_id == player_id and e.x is not None]
        out["touch_map"] = heat[-150:]
    out["memories"] = await c.memory.recall(p.name, entities=[player_id], k=3)
    return out
