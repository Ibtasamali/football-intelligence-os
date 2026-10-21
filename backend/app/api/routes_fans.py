"""Fan profiles (personalisation) and knowledge base management."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import container
from app.core.security import Principal, audit, get_principal, require_role
from app.models.domain import FanProfile, new_id
from app.schemas.api import FanProfileUpdate, KnowledgeTextRequest
from app.services.doc_intel import DocumentIntelligence, chunk

router = APIRouter(tags=["fans", "knowledge"])


@router.get("/api/fans")
async def list_fans(c=Depends(container), principal: Principal = Depends(get_principal)):
    return {"fans": await c.db.find("fan_profiles", {"tenant_id": principal.tenant_id})}


@router.get("/api/fans/{user_id}")
async def get_fan(user_id: str, c=Depends(container), principal: Principal = Depends(get_principal)):
    doc = await c.db.find_one("fan_profiles", {"tenant_id": principal.tenant_id, "user_id": user_id})
    if not doc:
        raise HTTPException(404, "fan not found")
    doc["memories"] = await c.memory.recall("fan conversation preferences", user_id=user_id, kinds=["conversation"], k=5)
    return doc


@router.put("/api/fans/{user_id}")
async def upsert_fan(user_id: str, body: FanProfileUpdate, c=Depends(container), principal: Principal = Depends(get_principal)):
    current = await c.db.find_one("fan_profiles", {"tenant_id": principal.tenant_id, "user_id": user_id}) or {}
    merged = FanProfile(**{**current, "user_id": user_id, "tenant_id": principal.tenant_id,
                           **{k: v for k, v in body.model_dump().items() if v is not None}})
    await c.db.upsert("fan_profiles", {"tenant_id": principal.tenant_id, "user_id": user_id}, merged.model_dump(mode="json"))
    audit("fan_profile_updated", principal, user_id=user_id)
    return merged.model_dump(mode="json")


@router.get("/api/knowledge/search")
async def knowledge_search(q: str, c=Depends(container)):
    hist = await c.vectors.search("historical_matches", q, 4)
    lib = await c.vectors.search("knowledge_documents", q, 4)
    strip = lambda d: {k: v for k, v in d.items() if k != "embedding"}  # noqa: E731
    return {"historical_matches": [strip(d) for d in hist], "knowledge_documents": [strip(d) for d in lib]}


@router.post("/api/knowledge/text")
async def knowledge_text(req: KnowledgeTextRequest, c=Depends(container), principal: Principal = Depends(require_role("analyst"))):
    return await _index(c, principal, req.title, req.text, req.teams, req.patterns, "text")


@router.post("/api/knowledge/upload")
async def knowledge_upload(file: UploadFile = File(...), title: str = Form(...), teams: str = Form(""), patterns: str = Form(""),
                           c=Depends(container), principal: Principal = Depends(require_role("analyst"))):
    di = DocumentIntelligence(c.settings)
    data = await file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "File too large")
    try:
        text = await di.extract_text(data, file.content_type or "application/pdf")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Document Intelligence unavailable: {exc}") from exc
    return await _index(c, principal, title, text, [t for t in teams.split(",") if t], [p for p in patterns.split(",") if p],
                        "azure-document-intelligence")


async def _index(c, principal, title, text, teams, patterns, via):
    pieces = chunk(text)
    base = new_id("doc")
    docs = [{"doc_id": f"{base}_{i}", "title": f"{title} (part {i + 1})", "text": f"{title}. {p}", "teams": teams,
             "patterns": patterns, "players": [], "collection": "knowledge_documents", "kind": "uploaded_report",
             "source": f"Uploaded report via {via}", "synthetic": False, "tenant_id": principal.tenant_id,
             "created_at": time.time()} for i, p in enumerate(pieces)]
    await c.vectors.index_documents("knowledge_documents", docs)
    audit("knowledge_indexed", principal, title=title, chunks=len(docs))
    return {"indexed_chunks": len(docs), "doc_ids": [d["doc_id"] for d in docs], "via": via}
