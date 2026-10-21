"""Evidence packaging and claim verification.

`build_evidence` assembles the only facts an LLM may use. `verify_output` then checks the LLM's output
against that package: cited event IDs must exist, metric references must exist, every number written
must be traceable to the evidence, historical matches must have been retrieved, and predictions must
not be stated as certainties.
"""
from __future__ import annotations

import re

from app.cag.context import compact_event
from app.data.teams import PLAYERS, TEAMS

NUM_RE = re.compile(r"(?<![A-Za-z])(\d+(?:\.\d+)?)")
CERTAIN_FUTURE = re.compile(r"\b(will (score|win|concede|equali[sz]e)|is going to (score|win)|guaranteed|certain to)\b", re.I)
MATCHDAY_RE = re.compile(r"matchday\s+(\d+)", re.I)


def flatten(obj, prefix: str = "", out: dict | None = None) -> dict:
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:30]):
            flatten(v, f"{prefix}[{i}]", out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix] = obj
    return out


ID_RE = re.compile(r"\b(?:sbp?\d+|(?:azc|tha)_\d+|ev_[0-9a-f]{6,}|[\w-]+-e\d{5})\b")
COORD_RE = re.compile(r"\(\s*\d{1,3}(?:\.\d+)?\s*,\s*\d{1,3}(?:\.\d+)?\s*\)|\bx\s*=\s*\d|\by\s*=\s*\d")
KEEP_ID_KEYS = {"event_id", "evidence_event_ids", "valid_event_ids", "event_ids", "snapshot_event", "insight_id",
                "memory_id", "doc_id", "source_events", "sb_event"}


def humanize(obj, key: str | None = None):
    """Replace player/team ids with names everywhere the LLM reads prose-like values."""
    if key in KEEP_ID_KEYS:
        return obj
    if isinstance(obj, dict):
        return {k: humanize(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [humanize(v, key) for v in obj]
    if isinstance(obj, str):
        if obj in PLAYERS:
            return PLAYERS[obj].name
        if obj in TEAMS:
            return TEAMS[obj].name
    return obj


def _strip_heavy(output: dict) -> dict:
    return {k: v for k, v in output.items() if k not in ("series", "trace", "edges", "plan")}


def build_evidence(state: dict, runtime) -> dict:
    eng = runtime.engine
    ev = state.get("event_obj")
    results = state.get("agent_results", {})
    analysis = {name: humanize(_strip_heavy(r["output"])) for name, r in results.items()
                if r.get("status") in ("complete", "cached") and name not in
                ("rag_retrieval", "mag_memory", "cag_context", "prediction", "expert_analyst", "fact_verification")}
    window_events = [compact_event(e) for e in eng.window(90, until=ev.game_seconds if ev else None)[-10:]]
    docs = results.get("rag_retrieval", {}).get("output", {}).get("documents", [])
    mems = results.get("mag_memory", {}).get("output", {}).get("memories", [])
    preds = state.get("predictions", [])
    frozen = state.get("frozen") or {}
    score = frozen.get("score") or eng.score
    until = ev.game_seconds if ev else None
    goals = [{"clock": g.clock, "team": TEAMS[g.team_id].name, "scorer": PLAYERS[g.player_id].name if g.player_id in PLAYERS else None,
              "assist": PLAYERS[g.related_player_id].name if g.related_player_id in PLAYERS else None, "event_id": g.event_id}
             for g in eng.events if g.type.value == "GOAL" and (until is None or g.game_seconds <= until)]
    evidence = {
        "match": {"score_text": f"{TEAMS[eng.home].name} {score[eng.home]}–{score[eng.away]} {TEAMS[eng.away].name}",
                  "clock": ev.clock if ev else (eng.events[-1].clock if eng.events else "00:00"),
                  "goals_so_far": goals,
                  "note": "score_text is the score immediately after this event"},
        "event": compact_event(ev) if ev else None,
        "recent_events": window_events,
        "patterns": [{k: p[k] for k in ("type", "team_id", "summary", "metrics", "confidence", "evidence_event_ids")}
                     for p in (state.get("new_patterns") or [])] +
                    [{"type": p["type"], "team_id": p["team_id"], "summary": p["summary"], "metrics": p["metrics"]}
                     for p in runtime.patterns.active_list() if p["type"] not in {n["type"] for n in state.get("new_patterns") or []}][:2],
        "ended_patterns": [{k: p[k] for k in ("type", "team_id", "summary")} for p in state.get("ended_patterns") or []],
        "analysis": analysis,
        "predictions": preds,
        "documents": [{"doc_id": d["doc_id"], "title": d["title"], "source": d["source"], "synthetic": d.get("synthetic"),
                       "snippet": d["snippet"][:420]} for d in docs[:3]],
        "memories": [{"memory_id": m["memory_id"], "text": m["text"], "source": m.get("source")} for m in mems[:3]],
        "question": state.get("question"),
    }
    if state.get("mode") == "query":
        focus = next((i for i in runtime.insights if i.insight_id == state.get("focus_insight_id")), None)
        if focus:
            evidence["focus_moment"] = {"clock": f"{focus.minute:02d}:{focus.second:02d}", "category": focus.category,
                                        "headline": focus.headline, "explanation": focus.explanations.get("professional", ""),
                                        "patterns": [p.get("summary") for p in focus.patterns],
                                        "event_ids": focus.provenance.source_events[:8]}
        evidence["match_totals"] = {TEAMS[t].name: {k: v for k, v in d.items() if k in (
            "possession", "xg", "shots", "ppda", "field_tilt", "high_turnovers", "pass_completion", "goals")} for t, d in eng.totals().items()}
        evidence["top_players"] = [{k: r[k] for k in ("name", "position", "influence", "goals", "assists", "xg", "xa",
                                                       "progressive_actions", "recoveries")} for r in eng.player_influence(top=3)]
    ids = set(evidence.get("focus_moment", {}).get("event_ids", []))
    if ev:
        ids.add(ev.event_id)
    for e in window_events:
        ids.add(e["event_id"])
    for p in state.get("new_patterns") or []:
        ids.update(p.get("evidence_event_ids", []))
    for r in results.values():
        ids.update(r.get("evidence_event_ids", []))
    evidence = humanize(evidence)
    evidence["valid_event_ids"] = sorted(ids)
    evidence["metrics"] = {k: v for k, v in flatten({"analysis": analysis, "patterns": evidence["patterns"],
                                                       "predictions": preds}).items()}
    return evidence


def allowed_numbers(evidence: dict) -> set[float]:
    vals: set[float] = set()

    def add(v: float):
        for x in (v, round(v, 1), round(v, 2), float(round(v)), abs(v)):
            vals.add(round(x, 2))
        if -1.0 <= v <= 1.0:
            for x in (v * 100, round(v * 100), round(v * 100, 1), abs(v * 100), round(abs(v * 100))):
                vals.add(round(x, 2))

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, bool):
            return
        elif isinstance(o, (int, float)):
            add(float(o))
        elif isinstance(o, str):
            for m in NUM_RE.findall(o):
                add(float(m))

    walk({k: v for k, v in evidence.items() if k not in ("valid_event_ids", "metrics")})
    vals.update(float(i) for i in range(0, 12))  # counts like "two", "3v2", formation digits, "1-0"
    vals.update({90.0, 45.0, 10.0, 5.0, 15.0})   # standard time horizons
    return vals


def _number_ok(n: float, allowed: set[float]) -> bool:
    return any(abs(n - a) <= max(0.051, 0.012 * abs(a)) for a in allowed)


def verify_output(output: dict, evidence: dict, engine=None) -> dict:
    allowed = allowed_numbers(evidence)
    valid_ids = set(evidence.get("valid_event_ids", []))
    doc_titles = " ".join([d["title"] for d in evidence.get("documents", [])]
                          + [m["text"] for m in evidence.get("memories", [])]
                          + [str(evidence.get("focus_moment", ""))])
    doc_titles = re.sub(r"Matchdays ((?:\d+(?:, | and )?)+)", lambda m: " ".join(f"Matchday {n}" for n in re.findall(r"\d+", m.group(1))), doc_titles)
    issues: list[str] = []
    verified, unverified = [], []

    def check_text(text: str, where: str) -> list[str]:
        problems = []
        for m in NUM_RE.findall(text or ""):
            if not _number_ok(float(m), allowed):
                problems.append(f"{where}: number {m} not found in evidence")
        for md in MATCHDAY_RE.findall(text or ""):
            if f"Matchday {md}" not in doc_titles and f"Matchday {int(md):02d}" not in doc_titles:
                problems.append(f"{where}: Matchday {md} not in retrieved documents")
        if CERTAIN_FUTURE.search(text or ""):
            problems.append(f"{where}: prediction stated as certainty")
        if COORD_RE.search(text or ""):
            problems.append(f"{where}: raw coordinates exposed — describe the area instead")
        if where != "claim" and ID_RE.search(text or ""):
            problems.append(f"{where}: internal identifier exposed ({ID_RE.search(text).group(0)}) — use names")
        return problems

    for c in output.get("claims", []) or []:
        if not isinstance(c, dict):
            c = {"text": str(c), "event_ids": [], "metric_refs": []}
        text = str(c.get("text") or "")
        p = check_text(text, "claim")
        bad_ids = [i for i in (c.get("event_ids") or []) if i not in valid_ids and not (engine and i in engine.by_id)]
        if bad_ids:
            p.append(f"claim cites unknown events {bad_ids}")
        refs = c.get("metric_refs") or []
        keys = evidence.get("metrics", {})
        bad_refs = [r for r in refs if r not in keys and not any(k.endswith("." + r) or k.endswith(r) or k.startswith(r + ".")
                                                                 or ("." + r + ".") in k for k in keys)]
        if bad_refs and len(bad_refs) == len(refs):
            p.append(f"claim cites unknown metrics {bad_refs[:3]}")
        c = {**c, "verified": not p, "reason": "; ".join(p) if p else "numbers, events and sources match evidence"}
        (verified if not p else unverified).append(c)
        issues += p

    texts = dict(output.get("explanations", {}) or {})
    texts["headline"] = output.get("headline", "")
    texts["commentary"] = output.get("commentary", "")
    texts["historical_note"] = output.get("historical_note", "")
    for k, t in texts.items():
        issues += check_text(t or "", k)

    names = {p.name for p in PLAYERS.values()} | {t.name for t in TEAMS.values()}
    surnames = {n.split()[-1] for n in names}
    for k, t in texts.items():
        for full in re.findall(r"\b([A-Z][a-zà-ÿ]+ [A-Z][a-zà-ÿ]+(?:-[A-Z][a-zà-ÿ]+)?)\b", t or ""):
            first, last = full.split(" ", 1)
            if last in surnames and full not in names and not any(full in n for n in names):
                issues.append(f"{k}: unknown person '{full}'")

    total = len(verified) + len(unverified)
    if output.get("claims") is not None and total == 0 and output.get("headline"):
        issues.append("claims: no atomic claims provided — list 2–4 factual claims with event_ids")
    score = (len(verified) / total) if total else (0.7 if not issues else 0.4)
    passed = not issues or (score >= 0.67 and len(issues) <= 1)
    return {"passed": passed, "issues": issues[:12], "verified_claims": verified, "unverified_claims": unverified,
            "claim_support": round(score, 2)}


def core_claims(evidence: dict) -> list[dict]:
    """Deterministic claims built straight from the evidence (true by construction), so every insight can show
    verified facts in the WHY? panel even if the model's own claims were rejected."""
    out = []
    ev = evidence.get("event") or {}
    interp = (evidence.get("analysis") or {}).get("event_interpretation") or {}
    if interp.get("description") and ev.get("event_id"):
        out.append({"text": interp["description"], "event_ids": [ev["event_id"]], "metric_refs": []})
    for p in (evidence.get("patterns") or [])[:2]:
        ids = p.get("evidence_event_ids") or []
        if p.get("summary"):
            out.append({"text": p["summary"], "event_ids": ids[:4], "metric_refs": []})
    gp = (evidence.get("analysis") or {}).get("goal_probability") or {}
    if gp.get("conversion_note") and ev.get("event_id"):
        out.append({"text": gp["conversion_note"], "event_ids": [ev["event_id"]], "metric_refs": []})
    if evidence.get("match", {}).get("score_text") and ev.get("type") == "GOAL":
        out.append({"text": f"Score after the goal: {evidence['match']['score_text']}", "event_ids": [ev["event_id"]], "metric_refs": []})
    return out
