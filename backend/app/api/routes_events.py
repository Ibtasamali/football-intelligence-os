"""External event ingestion (live data provider → pipeline)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import container, runtime_or_404
from app.core.security import Principal, audit, require_role
from app.models.domain import MatchEvent

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("")
async def ingest_event(event: MatchEvent, c=Depends(container), principal: Principal = Depends(require_role("analyst"))):
    runtime_or_404(c, event.match_id)
    result = await c.ingest(event)
    audit("event_ingested", principal, match_id=event.match_id, event_id=event.event_id)
    return {"accepted": True, "event_id": event.event_id, **result}
