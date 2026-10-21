"""Calibrate pattern thresholds on real matches.

For every match in the corpus we replay events through the tactical engine and sample each detector's raw
features every 60 s of game time for both teams. Thresholds are then chosen from feature quantiles so each
pattern is active in ~7% of windows: a pattern means "unusual for real international football", not "present".

  python -m eval.calibrate      → app/tactical/profiles/statsbomb.json + eval/results/features.json
"""
from __future__ import annotations

import asyncio
import json
import time

import numpy as np

from eval.corpus import load_corpus
from app.tactical.engine import TacticalEngine
from app.tactical.patterns import PROFILE_DIR, feat_block, feat_flank, feat_midfield, feat_press, feat_transition

TARGET_RATE = 0.07


def sample_features(match, events) -> list[dict]:
    eng = TacticalEngine(match.match_id, match.home_team_id, match.away_team_id)
    rows, next_t = [], 300
    for e in events:
        eng.update(e)
        if e.game_seconds >= next_t and e.positions:
            next_t = e.game_seconds + 60
            ws = eng.window_stats(300)
            for tid in (eng.home, eng.away):
                r = {"match": match.match_id, "team": tid, "t": e.game_seconds}
                if (f := feat_press(eng, tid, ws)):
                    r.update(press_ppda=f["ppda"], press_opp_half=f["opp_half"], press_defx=f["defx"])
                if (f := feat_flank(eng, tid)):
                    r.update(flank_share=f["share"], flank_actions=f["actions"])
                if (f := feat_block(eng, tid)):
                    r.update(block_line=f["line"], block_drop=f["drop"])
                f = feat_transition(eng, tid)
                r.update(trans_fast=f["fast"], trans_ratio=f["ratio"], trans_line=f["line"])
                if (f := feat_midfield(eng, tid)):
                    r.update(mid_avg=f["avg"])
                rows.append(r)
    return rows


def col(rows, k):
    return np.array([r[k] for r in rows if r.get(k) is not None], dtype=float)


def rate(rows, pred) -> float:
    return float(np.mean([pred(r) for r in rows])) if rows else 0.0


def fit(rows) -> tuple[dict, dict]:
    th, rates = {}, {}
    Q = lambda k, q: float(np.quantile(col(rows, k), q))  # noqa: E731

    def search(make, pred):
        best = None
        for q in np.linspace(0.02, 0.45, 44):
            t = make(q)
            r = rate(rows, lambda row: pred(row, t))
            if best is None or abs(r - TARGET_RATE) < abs(best[1] - TARGET_RATE):
                best = (t, r)
        return best

    press, r = search(lambda q: {"press_ppda_max": Q("press_ppda", q), "press_opp_half_min": Q("press_opp_half", 1 - q * 1.5),
                                 "press_defx_min": Q("press_defx", 0.5)},
                      lambda row, t: row.get("press_ppda") is not None and row["press_ppda"] <= t["press_ppda_max"]
                      and row["press_opp_half"] >= t["press_opp_half_min"] and row["press_defx"] >= t["press_defx_min"])
    th.update(press); rates["HIGH_PRESS"] = r
    flank, r = search(lambda q: {"flank_share_min": Q("flank_share", 1 - q), "flank_actions_min": Q("flank_actions", 0.3)},
                      lambda row, t: row.get("flank_share") is not None and row["flank_share"] >= t["flank_share_min"]
                      and row["flank_actions"] >= t["flank_actions_min"])
    th.update(flank); rates["FLANK_OVERLOAD"] = r
    block, r = search(lambda q: {"block_line_max": Q("block_line", q * 1.6), "block_drop_min": Q("block_drop", 1 - q * 1.6)},
                      lambda row, t: row.get("block_line") is not None and row["block_line"] <= t["block_line_max"]
                      and row["block_drop"] >= t["block_drop_min"])
    th.update(block); rates["DEEP_BLOCK"] = r
    trans, r = search(lambda q: {"trans_fast_min": max(2.0, Q("trans_fast", 1 - q)), "trans_ratio_min": 1.4,
                                 "trans_line_min": Q("trans_line", 0.35)},
                      lambda row, t: row["trans_fast"] >= t["trans_fast_min"] and row["trans_ratio"] >= t["trans_ratio_min"]
                      and row["trans_line"] >= t["trans_line_min"])
    th.update(trans); rates["TRANSITION_VULNERABILITY"] = r
    mid, r = search(lambda q: {"mid_avg_min": Q("mid_avg", 1 - q)},
                    lambda row, t: row.get("mid_avg") is not None and row["mid_avg"] >= t["mid_avg_min"])
    th.update(mid); rates["MIDFIELD_SUPERIORITY"] = r
    return {k: round(v, 3) for k, v in th.items()}, {k: round(v, 3) for k, v in rates.items()}


async def main():
    t0 = time.time()
    corpus = await load_corpus()
    print(f"loaded {len(corpus)} real matches in {time.time() - t0:.0f}s")
    rows = []
    for m, evs, label in corpus:
        rows += sample_features(m, evs)
    print(f"{len(rows)} team-window samples")
    th, rates = fit(rows)
    summary = {k: {"p10": round(float(np.quantile(col(rows, k), 0.1)), 2), "p50": round(float(np.quantile(col(rows, k), 0.5)), 2),
                   "p90": round(float(np.quantile(col(rows, k), 0.9)), 2)}
               for k in ("press_ppda", "press_opp_half", "press_defx", "flank_share", "flank_actions", "block_line",
                         "block_drop", "trans_fast", "trans_line", "mid_avg")}
    PROFILE_DIR.mkdir(exist_ok=True)
    (PROFILE_DIR / "statsbomb.json").write_text(json.dumps({
        "thresholds": th, "window_activation_rate": rates, "target_rate": TARGET_RATE, "samples": len(rows),
        "matches": [label for _, _, label in corpus], "feature_quantiles": summary,
        "source": "StatsBomb Open Data (FIFA World Cup 2022, UEFA Euro 2024), demo matches excluded"}, indent=2))
    print(json.dumps({"thresholds": th, "rates": rates}, indent=2))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
