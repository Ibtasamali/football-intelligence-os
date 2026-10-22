"""Football Intelligence OS as an MCP server — lets GitHub Copilot (VS Code agent mode) or any MCP client use the
match-intelligence agents as tools.

  stdio (VS Code / Copilot):  .venv/bin/python mcp_server.py
  HTTP:                       .venv/bin/python mcp_server.py --http   → http://127.0.0.1:8078/mcp

The tools call the running FIOS API (FIOS_API, default http://localhost:8077), so every answer goes through the same
LangGraph agents, verification and provenance as the app.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

from mcp.server.mcpserver import MCPServer

API = os.getenv("FIOS_API", "http://localhost:8077")
mcp = MCPServer("football-intelligence-os", title="Football Intelligence OS",
                instructions="Live, explainable football match intelligence on synthetic, football-realistic data. "
                             "Use match_status first, then insights/explanations, ask_match for questions, what_if for tactics.")


def _call(path: str, body: dict | None = None, timeout: int = 120):
    req = urllib.request.Request(API + path, method="POST" if body is not None else "GET",
                                 headers={"content-type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


@mcp.tool(description="Current score, clock, momentum and active tactical patterns of a match.")
def match_status(match_id: str = "live-demo") -> dict:
    m = _call(f"/api/matches/{match_id}")
    ctx = m.get("context") or {}
    return {"score": ctx.get("score_text"), "clock": ctx.get("clock"), "momentum": ctx.get("momentum"),
            "active_patterns": [p["summary"] for p in ctx.get("active_patterns", [])], "replay": m.get("replay")}


@mcp.tool(description="Latest AI insights (headline, minute, category, confidence). Optional category filter, e.g. GOAL.")
def list_insights(match_id: str = "live-demo", limit: int = 8, category: str = "") -> list[dict]:
    q = "?limit=200" + (f"&category={urllib.parse.quote(category)}" if category else "")
    ins = _call(f"/api/matches/{match_id}/insights{q}")["insights"]
    ins = sorted(ins, key=lambda i: (i["minute"], i["second"]))[-limit:]
    return [{"insight_id": i["insight_id"], "minute": i["minute"], "category": i["category"], "headline": i["headline"],
             "confidence": i["provenance"]["confidence"]} for i in ins]


@mcp.tool(description="Explain one insight at a knowledge level (beginner|intermediate|advanced|professional) with its verified claims and evidence.")
def explain_insight(insight_id: str, level: str = "intermediate") -> dict:
    ins = _call(f"/api/insights/{insight_id}")
    why = _call(f"/api/insights/{insight_id}/why")
    return {"headline": ins["headline"], "explanation": ins["explanations"].get(level, ""),
            "verified_claims": [c["text"] for c in why["claims"]], "agents_used": why["agents_used"],
            "retrieved_documents": [d["title"] for d in why["retrieved_documents"]], "confidence": why["confidence"]}


@mcp.tool(description="Ask the match copilot any question (routes through the 30-agent LangGraph with RAG, memory and fact verification). Optional language code, e.g. es, ur, ar.")
def ask_match(question: str, match_id: str = "live-demo", language: str = "en") -> dict:
    a = _call("/api/voice/query", {"match_id": match_id, "text": question, "user_id": "copilot", "language": language})["answer"]
    loc = a.get("localized") or {}
    return {"answer": loc.get("explanation") or a["statistics"].get("answer"), "headline": loc.get("headline") or a["headline"],
            "confidence": a["provenance"]["confidence"], "graph_path": a["provenance"]["graph_path"]}


@mcp.tool(description="Tactical metrics: possession, xG, PPDA, field tilt, live formations and predictions.")
def get_tactics(match_id: str = "live-demo") -> dict:
    t = _call(f"/api/matches/{match_id}/tactics")
    keep = ("possession", "xg", "shots", "ppda", "field_tilt", "high_turnovers")
    return {"totals": {k: {m: v[m] for m in keep} for k, v in t["totals"].items()}, "formations": t["formations"],
            "predictions": [f"{p['label']}: {round(p['probability'] * 100)}%" for p in t["predictions"]],
            "active_patterns": [p["summary"] for p in t["active_patterns"]]}


@mcp.tool(description="What-if: move a player (by name) dx/dy metres on the current frozen frame and get the recomputed dangerous space, passing options and an explanation. dx>0 = towards the home team's attacking goal.")
def what_if(player_name: str, dx: float, dy: float = 0.0, match_id: str = "live-demo") -> dict:
    m = _call(f"/api/matches/{match_id}")
    roster = {p["name"].lower(): p["player_id"] for p in m["roster"]}
    pid = next((v for k, v in roster.items() if player_name.lower() in k), None)
    if not pid:
        return {"error": f"Unknown player '{player_name}'"}
    pos = next((p for p in (m.get("last_event") or {}).get("positions", []) if p["player_id"] == pid), None)
    if not pos:
        return {"error": "Player not on the pitch in the current frame"}
    r = _call(f"/api/matches/{match_id}/whatif", {"moves": {pid: [pos["x"] + dx, pos["y"] + dy]}})
    return {"delta": r["delta"], "explanation": r.get("explanation"), "clock": r["clock"]}


@mcp.tool(description="Recap Studio: social post, push notification, broadcast lower-third, newsletter and two-host podcast script (+MP3 URL).")
def generate_recap(match_id: str = "live-demo", language: str = "en") -> dict:
    r = _call(f"/api/matches/{match_id}/recap", {"language": language}, timeout=240)
    return {k: r.get(k) for k in ("headline", "social_post", "push_notification", "lower_third", "newsletter", "podcast", "podcast_url", "verification")}


@mcp.tool(description="Control the match replay: action = start | pause | jump (with minute).")
def control_match(action: str, minute: float = 0, match_id: str = "live-demo") -> dict:
    if action == "jump":
        return _call(f"/api/matches/{match_id}/replay-jump", {"minute": minute})
    return _call(f"/api/matches/{match_id}/replay/{action}", {})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8078) if "--http" in sys.argv else mcp.run()
