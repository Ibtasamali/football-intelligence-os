"""Real-match corpus from StatsBomb Open Data, shared by calibration and evaluation scripts."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.statsbomb import CURATED, fetch, load_match  # noqa: E402

COMPETITIONS = [(43, 106, 22), (55, 282, 10)]  # (competition, season, how many matches) — WC 2022, Euro 2024
DEMO_MATCHES = {c["sb_match_id"] for c in CURATED}


async def corpus_ids() -> list[tuple[int, int, int, str]]:
    out = []
    for comp, season, n in COMPETITIONS:
        matches = await fetch(f"matches/{comp}/{season}.json")
        pool = sorted((m for m in matches if m["match_id"] not in DEMO_MATCHES), key=lambda m: m["match_date"])
        step = max(1, len(pool) // n)
        for m in pool[::step][:n]:
            label = f"{m['home_team']['home_team_name']} {m['home_score']}–{m['away_score']} {m['away_team']['away_team_name']}"
            out.append((m["match_id"], comp, season, label))
    return out


async def load_corpus(limit: int | None = None):
    ids = await corpus_ids()
    if limit:
        ids = ids[:limit]
    sem = asyncio.Semaphore(4)

    async def one(mid, comp, season, label):
        async with sem:
            m, evs, info = await load_match(mid, comp, season, f"sb-{mid}")
            return m, evs, label

    return await asyncio.gather(*(one(*x) for x in ids))
