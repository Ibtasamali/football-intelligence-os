"""Insights and their explainability ("WHY?")."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import container
from app.cag.context import compact_event
from app.schemas.api import TranslateRequest

router = APIRouter(prefix="/api/insights", tags=["insights"])


async def _find(c, insight_id: str) -> dict:
    for rt in c.runtimes.values():
        for i in rt.insights:
            if i.insight_id == insight_id:
                return i.model_dump()
    doc = await c.db.find_one("insights", {"insight_id": insight_id})
    if not doc:
        raise HTTPException(404, "insight not found")
    return doc


@router.get("/{insight_id}")
async def get_insight(insight_id: str, c=Depends(container)):
    return await _find(c, insight_id)


@router.post("/{insight_id}/translate")
async def translate(insight_id: str, req: TranslateRequest, c=Depends(container)):
    """Verified translation of an insight's fan-facing text (shared cache: one translation per language)."""
    ins = await _find(c, insight_id)
    out = await c.localize(ins, req.language, req.level.value, req.persona.value)
    return {"insight_id": insight_id, **out["localized"]}


@router.get("/{insight_id}/why")
async def why(insight_id: str, c=Depends(container)):
    ins = await _find(c, insight_id)
    rt = c.runtimes.get(ins["match_id"])
    events = []
    if rt:
        for eid in ins["provenance"]["source_events"][:20]:
            e = rt.engine.by_id.get(eid)
            if e:
                events.append(compact_event(e))
    return {"insight_id": insight_id, "headline": ins["headline"], "claims": ins["claims"],
            "verification": ins.get("verification"), "evidence_events": events,
            "retrieved_documents": ins["provenance"]["retrieved_documents"], "memories": ins["provenance"]["memories"],
            "agents_used": ins["provenance"]["agents_used"], "model": ins["provenance"]["model"],
            "confidence": ins["provenance"]["confidence"], "graph_path": ins["provenance"]["graph_path"],
            "statistics": ins.get("statistics", {}).get("metrics", {}), "predictions": ins.get("predictions", []),
            "patterns": ins.get("patterns", []), "rag_trace": ins.get("statistics", {}).get("rag_trace"),
            "routing": ins.get("statistics", {}).get("routing"), "comparison": ins.get("statistics", {}).get("comparison")}
