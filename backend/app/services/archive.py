"""Real historical archive: earlier matches of both teams, analysed by our own tactical engine.

For a StatsBomb match we take each team's previous matches in the same competition, replay them through the
fast path (no LLM), and write one evidence-rich summary per match into `historical_matches` plus a
team-tendency memory into MAG. Every number in the archive is computed from real event data.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from app.core.logging import get_logger
from app.data.statsbomb import ATTRIBUTION, fetch, load_match, team_history
from app.data.teams import player_name, team_name
from app.models.domain import EventType
from app.tactical.engine import TacticalEngine
from app.tactical.patterns import PatternTracker

log = get_logger("archive")
SOURCE = "StatsBomb Open Data · analysed by the FIOS tactical engine"


def summarise(match, events) -> dict:
    eng = TacticalEngine(match.match_id, match.home_team_id, match.away_team_id)
    tracker = PatternTracker("statsbomb")
    starts = []
    for e in events:
        eng.update(e)
        for kind, p in tracker.update(eng):
            if kind == "start":
                starts.append((e.minute, p))
    h, a = match.home_team_id, match.away_team_id
    tot = eng.totals()
    goals = [f"{e.minute}' {player_name(e.player_id) if e.player_id else 'own goal'} ({team_name(e.team_id)})"
             for e in events if e.type == EventType.GOAL]
    stage = match.competition.split("·")[-1].strip()
    title = f"{match.competition.split('·')[0].strip()} · {stage} — {team_name(h)} {eng.score[h]}–{eng.score[a]} {team_name(a)}"
    if match.notes.get("penalties"):
        title += f" ({match.notes['penalties']})"
    lines = [f"{title}, played {match.notes['match_date']}.",
             f"Goals: {', '.join(goals) or 'none'}."]
    for tid in (h, a):
        d = tot[tid]
        lines.append(f"{team_name(tid)}: xG {d['xg']}, possession {round(d['possession'] * 100)}%, PPDA {d['ppda']}, "
                     f"field tilt {round(d['field_tilt'] * 100)}%, {d['high_turnovers']} high turnovers.")
    if starts:
        lines.append("Patterns detected: " + "; ".join(f"{m}' {p.summary}" for m, p in starts[:6]))
    infl = eng.player_influence(top=4)
    lines.append("Most influential: " + ", ".join(f"{r['name']} ({team_name(r['team_id'])})" for r in infl) + ".")
    winner = h if eng.score[h] > eng.score[a] else a if eng.score[a] > eng.score[h] else None
    return {
        "doc_id": f"sb_hist_{match.notes['sb_match_id']}", "title": title, "date": match.notes["match_date"],
        "teams": [h, a], "score": f"{eng.score[h]}–{eng.score[a]}", "winner": winner,
        "patterns": sorted({p.type for _, p in starts}),
        "pattern_by_team": {tid: sorted({p.type for _, p in starts if p.team_id == tid}) for tid in (h, a)},
        "players": [r["player_id"] for r in infl],
        "metrics": {tid: {k: tot[tid][k] for k in ("xg", "possession", "ppda", "field_tilt", "high_turnovers")} for tid in (h, a)},
        "text": " ".join(lines), "collection": "historical_matches", "source": SOURCE, "synthetic": False,
        "attribution": ATTRIBUTION,
    }


_POOL: ProcessPoolExecutor | None = None


def _archive_docs_worker(sb_match_id: int, competition_id: int, season_id: int, limit_per_team: int) -> list[dict]:
    """Runs in a separate process: replaying 12 matches is CPU-heavy and must never block the API event loop."""
    async def run() -> list[dict]:
        matches = await fetch(f"matches/{competition_id}/{season_id}.json")
        meta = next(m for m in matches if m["match_id"] == sb_match_id)
        prior = await team_history(meta, competition_id, season_id, limit_per_team)
        docs = []
        for pm in prior:
            try:
                m, evs, _ = await load_match(pm["match_id"], competition_id, season_id, f"hist-{pm['match_id']}")
                docs.append(summarise(m, evs))
            except Exception as exc:  # noqa: BLE001 — one bad file must not block the archive
                log.warning("archive_match_failed", sb_match_id=pm["match_id"], error=str(exc)[:200])
        return docs
    return asyncio.run(run())


async def build_archive(container, match, limit_per_team: int = 6) -> dict:
    global _POOL
    n = match.notes
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()
    docs = await loop.run_in_executor(_POOL, _archive_docs_worker, n["sb_match_id"], n["competition_id"],
                                      n["season_id"], limit_per_team)
    if docs:
        await container.vectors.index_documents("historical_matches", docs)
    # team tendencies → MAG
    for tid in (match.home_team_id, match.away_team_id):
        own = [d for d in docs if tid in d["teams"]]
        if not own:
            continue
        counts = Counter(p for d in own for p in d["pattern_by_team"].get(tid, []))
        results = Counter("won" if d["winner"] == tid else "drew" if d["winner"] is None else "lost" for d in own)
        tend = ", ".join(f"{p.replace('_', ' ').lower()} in {c} of {len(own)}" for p, c in counts.most_common(3)) or "no strong recurring pattern"
        await container.memory.remember(
            kind="team_history", entities=[tid], source=SOURCE, importance=0.8, memory_id=f"mem_sb_{tid}_{n['sb_match_id']}",
            text=(f"Before this match, {team_name(tid)} played {len(own)} {match.competition.split('·')[0].strip()} matches "
                  f"(won {results['won']}, drew {results['drew']}, lost {results['lost']}). Patterns detected most often: {tend}."))
    log.info("archive_built", match=match.match_id, docs=len(docs))
    return {"documents": len(docs), "titles": [d["title"] for d in docs]}
