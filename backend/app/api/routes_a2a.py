"""Agent2Agent (A2A) protocol endpoint: other agents (a broadcaster's agent, a club's scouting agent, an orchestrator)
can discover Football Intelligence OS via its Agent Card and send it tasks over JSON-RPC 2.0.

  GET  /.well-known/agent-card.json      Agent Card (skills, capabilities)
  POST /a2a                              JSON-RPC: message/send (A2A 0.3) and SendMessage (A2A 1.0)
                                         text parts; optional metadata.skill / match_id / language
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import container

router = APIRouter(tags=["a2a"])

SKILLS = [
    {"id": "match_qa", "name": "Match Q&A", "description": "Answer any question about the live match with verified, evidence-linked reasoning (30-agent LangGraph).",
     "tags": ["football", "analysis", "qa"], "examples": ["Why did Thames Athletic score?", "Who is the best player?"]},
    {"id": "match_status", "name": "Match status", "description": "Score, clock, momentum and active tactical patterns.", "tags": ["football", "live"]},
    {"id": "recap", "name": "Recap Studio", "description": "Social post, push notification, broadcast lower-third, newsletter and two-host podcast script, in 14 languages.",
     "tags": ["recap", "broadcast", "content"], "examples": ["/recap es"]},
]


def agent_card(base: str) -> dict:
    return {"protocolVersion": "0.3.0", "name": "Football Intelligence OS",
            "description": "Explainable, real-time football match intelligence on synthetic, football-realistic data.",
            "url": f"{base}/a2a", "preferredTransport": "JSONRPC", "version": "1.0.0",
            "supportedInterfaces": [{"url": f"{base}/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain", "application/json"], "skills": SKILLS}


@router.get("/.well-known/agent-card.json")
@router.get("/.well-known/agent.json")
async def card(request: Request):
    return agent_card(str(request.base_url).rstrip("/"))


def _err(id_, code, msg):
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": msg}})


@router.post("/a2a")
async def a2a(request: Request, c=Depends(container)):
    try:
        req = await request.json()
    except Exception:  # noqa: BLE001
        return _err(None, -32700, "Parse error")
    if not isinstance(req, dict) or req.get("jsonrpc") not in (None, "2.0"):
        return _err(req.get("id") if isinstance(req, dict) else None, -32600, "Invalid Request")
    id_, method, params = req.get("id"), req.get("method"), req.get("params") or {}
    if not isinstance(params, dict):
        return _err(id_, -32602, "Invalid params")
    if method not in ("message/send", "SendMessage"):
        return _err(id_, -32601, f"Method not found: {method}")
    v1 = method == "SendMessage"
    msg = params.get("message") or {}
    if not isinstance(msg, dict):
        return _err(id_, -32602, "Invalid message")
    parts = msg.get("parts", [])
    text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("kind", "text") == "text" and "text" in p).strip()
    meta = {**(params.get("metadata") or {}), **(msg.get("metadata") or {})}
    match_id = meta.get("match_id") or "live-demo"
    rt = c.runtimes.get(match_id)
    if rt is None:
        return _err(id_, -32602, f"Unknown match '{match_id}'")
    try:
        answer, data = await handle(c, rt, text, meta)
    except ValueError as exc:
        return _err(id_, -32602, str(exc))
    context_id = msg.get("contextId") or str(uuid.uuid4())
    if v1:  # A2A 1.0: SendMessageResponse{message}
        result = {"message": {"messageId": str(uuid.uuid4()), "contextId": context_id, "role": "ROLE_AGENT",
                              "parts": [{"text": answer}, {"data": data}]}}
    else:
        result = {"kind": "message", "role": "agent", "messageId": str(uuid.uuid4()), "contextId": context_id,
                  "parts": [{"kind": "text", "text": answer}, {"kind": "data", "data": data}]}
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


async def handle(c, rt, text: str, meta: dict) -> tuple[str, dict]:
    """Runs one A2A skill. Shared by the JSON-RPC endpoint and the in-process Agent Framework desk."""
    match_id = rt.match_id
    language = meta.get("language", "en")
    skill = meta.get("skill") or ("recap" if text.startswith("/recap") else "match_status" if text.lower() in ("status", "/status") else "match_qa")
    if skill not in {"recap", "match_status", "match_qa"}:
        raise ValueError(f"Unknown skill '{skill}'")
    if skill == "recap":
        if text.startswith("/recap") and len(text.split()) > 1:
            language = text.split()[1]
        r = await c.recap_service.build(rt, c.story_service.facts(rt), language)
        answer, data = r["social_post"], {k: r.get(k) for k in ("headline", "push_notification", "lower_third", "newsletter", "podcast", "podcast_url", "verification")}
    elif skill == "match_status":
        ctx = await c.cag.get(match_id) or {}
        answer = f"{ctx.get('score_text', '')} at {ctx.get('clock', '')}"
        data = {"momentum": ctx.get("momentum"), "active_patterns": [p["summary"] for p in ctx.get("active_patterns", [])]}
    else:
        if not text:
            raise ValueError("Empty question")
        ins = await c.ask(match_id, text, user_id="a2a-agent", language=language)
        loc = ins.get("localized") or {}
        answer = loc.get("explanation") or ins["statistics"].get("answer") or ins["headline"]
        data = {"headline": loc.get("headline") or ins["headline"], "confidence": ins["provenance"]["confidence"],
                "insight_id": ins["insight_id"], "graph_path": ins["provenance"]["graph_path"],
                "verified_claims": [cl["text"] for cl in ins.get("claims", [])]}
    return answer, {"skill": skill, **data}
