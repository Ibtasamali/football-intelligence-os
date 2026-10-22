"""Deterministic evaluations (no LLM): tactical pattern detection on held-out synthetic matches with known ground truth.

  python -m eval.deterministic   → eval/results/deterministic.json
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from app.data.synthetic import SCRIPT, MatchSimulator
from app.data.teams import AWAY_ID, HOME_ID
from app.tactical.engine import TacticalEngine
from app.tactical.patterns import PatternTracker

OUT = Path(__file__).parent / "results"


# ---------------------------------------------------------------- A. pattern detection vs scripted ground truth
def ground_truth() -> list[dict]:
    """Scripted tactical phases that a detector should find (derived from SCRIPT, never shown to the detectors)."""
    gt = []
    for tid, phases in SCRIPT.items():
        for ph in phases:
            if ph.press >= 0.85:
                gt.append({"type": "HIGH_PRESS", "team": tid, "start": ph.start, "end": ph.end})
            if abs(ph.flank) >= 0.6:
                gt.append({"type": "FLANK_OVERLOAD", "team": tid, "start": ph.start, "end": ph.end})
            if ph.block <= 20:
                gt.append({"type": "DEEP_BLOCK", "team": tid, "start": ph.start, "end": ph.end})
            if (ph.fb_push >= 20 and ph.press >= 0.6) or ph.block >= 40:  # high line / full-backs high → space behind
                gt.append({"type": "TRANSITION_VULNERABILITY", "team": tid, "start": ph.start, "end": min(91, ph.end)})
    return gt


def eval_patterns(seeds=range(100, 130), tol_before=1, tol_after=3) -> dict:
    gt = ground_truth()
    per_type = defaultdict(lambda: {"tp": 0, "fp": 0, "found": 0, "windows": 0, "latency": []})
    unscripted = Counter()
    for seed in seeds:
        evs = MatchSimulator(f"eval-{seed}", seed).generate()
        eng = TacticalEngine("e", HOME_ID, AWAY_ID)
        tr = PatternTracker("synthetic")
        starts = []
        for e in evs:
            eng.update(e)
            starts += [(e.minute, p.type, p.team_id) for kind, p in tr.update(eng) if kind == "start"]
        matched_windows = set()
        for minute, ptype, team in starts:
            hit = next((i for i, g in enumerate(gt) if g["type"] == ptype and g["team"] == team
                        and g["start"] - tol_before <= minute <= g["end"] + tol_after), None)
            if hit is None:
                if any(g["type"] == ptype for g in gt):
                    per_type[ptype]["fp"] += 1
                else:
                    unscripted[ptype] += 1
            else:
                per_type[ptype]["tp"] += 1
                if hit not in matched_windows:
                    matched_windows.add(hit)
                    per_type[ptype]["latency"].append(max(0, minute - gt[hit]["start"]))
        for i, g in enumerate(gt):
            per_type[g["type"]]["windows"] += 1
            per_type[g["type"]]["found"] += int(i in matched_windows)
    out = {}
    for t, d in per_type.items():
        prec = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else None
        rec = d["found"] / d["windows"] if d["windows"] else None
        out[t] = {"precision": round(prec, 3) if prec is not None else None, "recall": round(rec, 3) if rec is not None else None,
                  "detections": d["tp"] + d["fp"], "scripted_windows": d["windows"],
                  "median_latency_min": float(np.median(d["latency"])) if d["latency"] else None}
    tot_tp = sum(d["tp"] for d in per_type.values())
    tot_fp = sum(d["fp"] for d in per_type.values())
    tot_found = sum(d["found"] for d in per_type.values())
    tot_win = sum(d["windows"] for d in per_type.values())
    return {"seeds": len(list(seeds)), "held_out": "seeds 100–129 (thresholds were tuned on seed 11 only)",
            "per_pattern": out, "micro_precision": round(tot_tp / max(1, tot_tp + tot_fp), 3),
            "micro_recall": round(tot_found / max(1, tot_win), 3), "unscripted_detections": dict(unscripted),
            "tolerance": f"detection may start {tol_before} min before to {tol_after} min after the scripted window"}


async def main():
    t0 = time.time()
    res = {"patterns_synthetic": eval_patterns()}
    print("A done", json.dumps(res["patterns_synthetic"], indent=1)[:1500])
    res["runtime_s"] = round(time.time() - t0, 1)
    OUT.mkdir(exist_ok=True)
    (OUT / "deterministic.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
