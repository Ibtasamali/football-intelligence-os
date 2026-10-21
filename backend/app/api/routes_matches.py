"""Matches: lifecycle, replay control, insights, timeline, tactics, story."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import container, runtime_or_404
from app.agents.analysis_agents import FormationAgent
from app.cag.context import compact_event, roster, team_meta
from app.core.security import Principal, audit, get_principal
from app.data.synthetic import generate_demo_match
from app.data.teams import AWAY_ID, HOME_ID
from app.models.domain import Match
from app.prediction.models import predict
from app.schemas.api import CreateMatchRequest, JumpRequest, ReplaySpeedRequest
from app.data.statsbomb import ATTRIBUTION, CURATED, load_match
from app.services.archive import build_archive
from app.services.replay import SYNTHETIC_JUMPS, ReplayController, real_match_pacing

router = APIRouter(prefix="/api/matches", tags=["matches"])
TIMELINE_CATEGORIES = {"GOAL", "TURNING_POINT", "TACTICAL_SHIFT", "HIGH_PRESS", "DANGEROUS_ATTACK", "PLAYER_IMPACT", "MOMENTUM_SHIFT"}


catalog_router = APIRouter(prefix="/api/catalog", tags=["matches"])


@catalog_router.get("/matches")
async def catalog(c=Depends(container)):
    out = [{"key": "demo", "label": "Azure City FC vs Thames Athletic · synthetic match", "source": "synthetic"}]
    if c.settings.enable_real_data:
        out += [{"key": x["key"], "label": x["label"], "source": "statsbomb", "attribution": ATTRIBUTION} for x in CURATED]
    return {"matches": out}


@router.post("")
async def create_match(req: CreateMatchRequest, c=Depends(container), principal: Principal = Depends(get_principal)):
    old = getattr(c, "replays", {}).get(req.match_id)
    if old:
        old.stop()
    if req.source == "statsbomb" and not c.settings.enable_real_data:
        raise HTTPException(403, "Real match data is disabled: this project runs on synthetic, football-realistic data")
    if req.source == "statsbomb":
        cur = next((x for x in CURATED if x["key"] == (req.statsbomb_key or req.match_id)), None)
        if not cur:
            raise HTTPException(404, "Unknown StatsBomb match key — see GET /api/catalog/matches")
        try:  # conversion is CPU-bound: run it off the event loop so the API stays responsive
            match, events, info = await asyncio.to_thread(
                lambda: asyncio.run(load_match(cur["sb_match_id"], cur["competition_id"], cur["season_id"], req.match_id)))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Could not load StatsBomb data: {exc}") from exc
        match.tenant_id = principal.tenant_id
        rt = await c.create_match(match)
        windows, jumps = real_match_pacing(events)
        rt.jump_points = jumps
        c.replays[req.match_id] = ReplayController(c, req.match_id, events, req.speed, req.director, slow_windows=windows)
        rt.archive_task = asyncio.create_task(_archive(c, match))
        if req.autostart:
            c.replays[req.match_id].start()
        audit("match_created", principal, match_id=req.match_id, source="statsbomb")
        return {"match": match.model_dump(), "events_available": len(events),
                "positions_from_360_pct": info["positions_from_360_pct"]}
    match = Match(match_id=req.match_id, home_team_id=HOME_ID, away_team_id=AWAY_ID, competition="Showcase League",
                  venue="Azure Arena", kickoff="2026-10-08T19:45:00Z", synthetic=req.source == "synthetic",
                  tenant_id=principal.tenant_id, score={HOME_ID: 0, AWAY_ID: 0})
    await c.create_match(match)
    if not hasattr(c, "replays"):
        c.replays = {}
    if req.source == "synthetic":
        events = generate_demo_match(req.match_id, req.seed)
        c.replays[req.match_id] = ReplayController(c, req.match_id, events, req.speed, req.director)
        c.runtimes[req.match_id].jump_points = SYNTHETIC_JUMPS
        if req.autostart:
            c.replays[req.match_id].start()
    audit("match_created", principal, match_id=req.match_id)
    return {"match": match.model_dump(), "events_available": len(c.replays.get(req.match_id).events) if req.source == "synthetic" else 0}


@router.get("")
async def list_matches(c=Depends(container)):
    return {"matches": [{**rt.match.model_dump(), "score": rt.engine.score,
                         "replay": c.replays[m].status() if m in getattr(c, "replays", {}) else None}
                        for m, rt in c.runtimes.items()]}


@router.get("/{match_id}")
async def get_match(match_id: str, c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    ctx = await c.cag.get(match_id)
    last = rt.engine.events[-1] if rt.engine.events else None
    ids = [rt.match.home_team_id, rt.match.away_team_id]
    return {"match": rt.match.model_dump(), "teams": team_meta(ids), "roster": roster(ids), "context": ctx,
            "home_id": rt.match.home_team_id, "away_id": rt.match.away_team_id,
            "jump_points": rt.jump_points or SYNTHETIC_JUMPS, "archive": rt.archive_status,
            "snapshot": rt.engine.snapshot(),
            "last_event": {**compact_event(last), "positions": [p.model_dump() for p in last.positions]} if last else None,
            "replay": c.replays[match_id].status() if match_id in getattr(c, "replays", {}) else None}


@router.get("/{match_id}/insights")
async def get_insights(match_id: str, limit: int = Query(50, le=500), category: str | None = None, c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    items = [i for i in rt.insights if not category or i.category == category]
    return {"insights": [i.model_dump() for i in items[-limit:]]}


@router.get("/{match_id}/timeline")
async def get_timeline(match_id: str, c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    items = []
    for i in rt.insights:
        if i.category in TIMELINE_CATEGORIES and (i.significance >= 0.4 or i.category == "GOAL"):
            items.append({"insight_id": i.insight_id, "clock": f"{i.minute:02d}:{i.second:02d}", "minute": i.minute,
                          "category": i.category, "headline": i.headline, "significance": i.significance,
                          "team_id": i.team_id, "event_id": i.event_id,
                          "turning_point": (i.statistics or {}).get("story", {}).get("turning_point", False)})
    return {"timeline": items, "momentum": [m for _, m in list(rt.engine.momentum_history)[::4]]}


@router.get("/{match_id}/tactics")
async def get_tactics(match_id: str, c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    eng = rt.engine
    last = eng.events[-1] if eng.events else None
    ev = next((e for e in reversed(eng.events) if e.positions), None)
    return {"active_patterns": rt.patterns.active_list(), "pattern_history": rt.patterns.history,
            "formations": {t: {"nominal": team_meta([t])[t]["formation"],
                               "live": FormationAgent.infer(ev.positions, t, eng.home) if ev else None} for t in (eng.home, eng.away)},
            "totals": eng.totals(), "window": eng.window_stats(300),
            "networks": {t: eng.passing_network(t, 15) for t in (eng.home, eng.away)},
            "influence": eng.player_influence(top=12), "momentum": eng.momentum_index(),
            "avg_positions": eng.average_positions(),
            "momentum_series": [{"t": t, "m": m} for t, m in list(eng.momentum_history)[::3]],
            "predictions": [p.model_dump() for p in predict(eng, last.type.value if last else "PASS", rt.patterns.active_list())],
            "substitutions": eng.substitutions}


@router.get("/{match_id}/events")
async def get_events(match_id: str, from_seq: int = 0, limit: int = Query(200, le=2000), positions: bool = False,
                     c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    evs = [e for e in rt.engine.events if e.seq >= from_seq][:limit]
    return {"events": [{**compact_event(e), **({"positions": [p.model_dump() for p in e.positions]} if positions else {})} for e in evs]}


@router.post("/{match_id}/events/positions")
async def get_event_positions(match_id: str, event_ids: list[str], c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    out = []
    for eid in event_ids[:40]:
        e = rt.engine.by_id.get(eid)
        if e:
            out.append({**compact_event(e), "positions": [p.model_dump() for p in e.positions]})
    return {"events": out}


@router.get("/{match_id}/replay")
async def replay_status(match_id: str, c=Depends(container)):
    r = getattr(c, "replays", {}).get(match_id)
    if not r:
        raise HTTPException(404, "No replay for this match")
    return r.status()


@router.post("/{match_id}/replay/{action}")
async def replay_control(match_id: str, action: str, c=Depends(container)):
    r = getattr(c, "replays", {}).get(match_id)
    if not r:
        raise HTTPException(404, "No replay for this match")
    if action == "start":
        r.start()
    elif action == "pause":
        r.pause()
    else:
        raise HTTPException(400, "action must be start or pause")
    return r.status()


@router.post("/{match_id}/replay-speed")
async def replay_speed(match_id: str, req: ReplaySpeedRequest, c=Depends(container)):
    r = getattr(c, "replays", {}).get(match_id)
    if not r:
        raise HTTPException(404, "No replay for this match")
    r.speed = req.speed
    if req.director is not None:
        r.director = req.director
    return r.status()


@router.post("/{match_id}/replay-jump")
async def replay_jump(match_id: str, req: JumpRequest, c=Depends(container)):
    r = getattr(c, "replays", {}).get(match_id)
    if not r:
        raise HTTPException(404, "No replay for this match")
    n = await r.jump_to(req.minute, req.seq)
    return {**r.status(), "fast_forwarded": n}


@router.get("/{match_id}/story")
async def get_story(match_id: str, c=Depends(container)):
    rt = runtime_or_404(c, match_id)
    if not rt.engine.events:
        raise HTTPException(409, "Match has no events yet")
    return await c.story_service.build(rt, tier="large")


async def _archive(c, match) -> None:
    rt = c.runtimes.get(match.match_id)
    try:
        if rt:
            rt.archive_status = {"status": "building"}
        res = await build_archive(c, match)
        if rt:
            rt.archive_status = {"status": "ready", **res}
        await c.broadcast(match.match_id, {"type": "archive_ready", **res})
    except Exception as exc:  # noqa: BLE001
        if rt:
            rt.archive_status = {"status": "failed", "error": str(exc)[:200]}


WHATIF_PROMPT = """You are a football tactics coach explaining a WHAT-IF experiment on a frozen match moment.
A user moved one or more players. Using ONLY the numbers in DATA (before → after), explain in plain language what
changed and why it matters. Never invent numbers and never mention coordinates. Mention the moved player(s) by name
and use football language (deeper, higher, wider, more central). Return JSON:
{"headline": "≤ 10 words", "text": "2–3 sentences"}"""


@router.post("/{match_id}/whatif")
async def whatif(match_id: str, body: dict, c=Depends(container)):
    """Counterfactual: move players on a frozen frame → recompute pitch control, dangerous space, passing options."""
    from app.agents.evidence import verify_output
    from app.tactical.whatif import simulate
    rt = runtime_or_404(c, match_id)
    eng = rt.engine
    ev = eng.by_id.get(body.get("event_id")) if body.get("event_id") else None
    if ev is None:
        ev = next((e for e in reversed(eng.events) if e.positions), None)
    if ev is None or not ev.positions:
        raise HTTPException(409, "No frame with player positions yet — start the match first")
    moves = {k: v for k, v in (body.get("moves") or {}).items() if isinstance(v, list) and len(v) == 2}
    attacking = eng.possession_at(ev) or eng.home
    res = await asyncio.to_thread(simulate, ev, eng.home, attacking, moves)
    res.update({"event_id": ev.event_id, "clock": ev.clock})
    if moves and body.get("explain", True):
        data = {k: res[k] for k in ("attacking_name", "carrier_name", "delta")}
        data["moved"] = [{"name": m["name"], "team": m["team"], "moved_m": m["moved_m"],
                          "direction": _direction(m, eng.home, rt.engine)} for m in res["moved"]]
        data["before"] = {k: v for k, v in res["before"].items() if k != "passing_options"}
        data["after"] = {k: v for k, v in res["after"].items() if k != "passing_options"}
        d = res["delta"]
        mv = ", ".join(m["name"] for m in res["moved"])

        def fallback():
            sign = "more" if d["dangerous_space_pct"] > 0 else "less"
            return {"headline": f"Moving {mv}: {abs(d['dangerous_space_pct'])} pts {sign} danger",
                    "text": (f"{res['attacking_name']} now control {res['after']['dangerous_space_pct']}% of the dangerous space "
                             f"(was {res['before']['dangerous_space_pct']}%) and have {res['after']['open_passing_options']} open passing "
                             f"options (was {res['before']['open_passing_options']}).")}
        out = await c.llm.complete_json(system=WHATIF_PROMPT, user="DATA:\n" + json.dumps(data, default=str), tier="small",
                                        fallback=fallback, max_tokens=300, temperature=0.3, interactive=True)
        check = verify_output({"headline": out.data.get("headline", ""), "explanations": {"text": out.data.get("text", "")}},
                              {"data": data, "valid_event_ids": []})
        res["explanation"] = out.data if check["passed"] else fallback()
        res["explanation"]["verified"] = check["passed"]
        res["explanation"]["model"] = out.model
    return res


def _direction(m: dict, home: str, eng) -> str:
    """Describe a move in football terms from the moved player's own team perspective."""
    from app.data.teams import PLAYERS
    team = PLAYERS[m["player_id"]].team_id if m["player_id"] in PLAYERS else home
    dx, dy = m["to"][0] - m["from"][0], m["to"][1] - m["from"][1]
    if team != home:
        dx, dy = -dx, -dy
    parts = []
    if abs(dx) >= 2:
        parts.append("higher up the pitch" if dx > 0 else "deeper towards own goal")
    if abs(dy) >= 2:
        parts.append("towards own right flank" if dy < 0 else "towards own left flank")
    return " and ".join(parts) or "a small adjustment"


recap_router = APIRouter(tags=["recap"])


@router.post("/{match_id}/recap")
async def recap(match_id: str, body: dict, c=Depends(container)):
    """Recap Studio: social post, push, lower-third, newsletter and two-voice podcast from verified facts."""
    rt = runtime_or_404(c, match_id)
    if not rt.engine.events:
        raise HTTPException(409, "Match has no events yet")
    facts = c.story_service.facts(rt)
    body = body or {}
    return await c.recap_service.build(rt, facts, body.get("language", "en"), audio=bool(body.get("audio", True)))


@router.post("/{match_id}/recap/podcast")
async def recap_podcast(match_id: str, body: dict, c=Depends(container)):
    """Voices an already-generated recap podcast script with two Azure neural voices."""
    runtime_or_404(c, match_id)
    return {"podcast_url": await c.recap_service.podcast((body or {}).get("podcast") or [], (body or {}).get("language", "en"))}


@recap_router.get("/api/recaps/{key}.mp3")
async def recap_audio(key: str):
    from fastapi.responses import FileResponse
    from app.services.recap import AUDIO_DIR
    if not key.isalnum():
        raise HTTPException(400, "bad key")
    f = AUDIO_DIR / f"{key}.mp3"
    if not f.exists():
        raise HTTPException(404, "not found")
    return FileResponse(f, media_type="audio/mpeg")


@recap_router.get("/api/reports/{key}.pdf")
async def coach_report_pdf(key: str):
    from fastapi.responses import FileResponse
    from app.services.coach_report import REPORT_DIR
    if not key.isalnum():
        raise HTTPException(400, "bad key")
    f = REPORT_DIR / f"{key}.pdf"
    if not f.exists():
        raise HTTPException(404, "not found")
    return FileResponse(f, media_type="application/pdf", filename=f"football-coach-report-{key}.pdf")


def _zone(tx: float, ty: float) -> str:
    third = "in their own third" if tx < 35 else "in midfield" if tx < 70 else "in the attacking third"
    if tx >= 88 and 14 <= ty <= 54:
        third = "inside the penalty area"
    side = "on the right" if ty < 22.7 else "on the left" if ty > 45.3 else "centrally"
    return f"{third}, {side}"


@router.get("/{match_id}/describe")
async def describe(match_id: str, c=Depends(container)):
    """Accessibility: a spoken description of the current situation built from data (zero tokens)."""
    from app.data.teams import player_name, team_name
    from app.tactical.engine import team_frame
    rt = runtime_or_404(c, match_id)
    eng = rt.engine
    ev = next((e for e in reversed(eng.events) if e.positions), None)
    if not ev:
        return {"text": "The match has not started yet."}
    h, a = eng.home, eng.away
    parts = [f"{ev.clock}. {team_name(h)} {eng.score[h]}, {team_name(a)} {eng.score[a]}."]
    poss = eng.possession_at(ev) or h
    bx, by = (ev.end_x, ev.end_y) if ev.end_x is not None else (ev.x or 52.5, ev.y or 34)
    tx, ty = team_frame(poss, h, bx, by)
    carrier = ev.related_player_id if ev.type.value == "PASS" and ev.outcome == "success" else ev.player_id
    who = f"{player_name(carrier)} has the ball" if carrier and ev.team_id == poss else f"{team_name(poss)} have the ball"
    parts.append(f"{who} for {team_name(poss)}, {_zone(tx, ty)}.")
    att = sum(1 for p in ev.positions if p.team_id == poss and team_frame(poss, h, p.x, p.y)[0] >= 52.5)
    dfd = sum(1 for p in ev.positions if p.team_id != poss and team_frame(poss, h, p.x, p.y)[0] >= 52.5)
    parts.append(f"{att} attackers against {dfd} defenders in the opponent half.")
    pats = rt.patterns.active_list()
    if pats:
        parts.append("Tactical picture: " + " ".join(p["summary"] for p in pats[:2]))
    mom = eng.momentum_index()
    parts.append(f"Momentum is with {team_name(h) if mom > 0.1 else team_name(a) if mom < -0.1 else 'neither side'}.")
    return {"text": " ".join(parts), "clock": ev.clock}
