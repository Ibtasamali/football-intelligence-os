"""Deterministic evaluations (no LLM): pattern detection, threshold generalisation, xG, prediction calibration.

  python -m eval.deterministic   → eval/results/deterministic.json
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from eval.corpus import load_corpus
from app.data.statsbomb import CURATED, load_match
from app.data.synthetic import SCRIPT, MatchSimulator
from app.data.teams import AWAY_ID, HOME_ID
from app.prediction.models import TRACKED, goal_threat
from app.tactical.engine import TacticalEngine
from app.tactical.patterns import PatternTracker
from app.tactical.xg import expected_goals

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


# ---------------------------------------------------------------- B. calibrated thresholds on held-out real matches
async def eval_generalisation() -> dict:
    prof = json.loads((Path(__file__).resolve().parents[1] / "app/tactical/profiles/statsbomb.json").read_text())
    rates = defaultdict(list)
    for cur in CURATED:  # demo matches were excluded from calibration
        m, evs, _ = await load_match(cur["sb_match_id"], cur["competition_id"], cur["season_id"], f"gen-{cur['key']}")
        eng = TacticalEngine(m.match_id, m.home_team_id, m.away_team_id)
        tr = PatternTracker("statsbomb")
        active_minutes = Counter()
        last_min = -1
        for e in evs:
            eng.update(e)
            tr.update(eng)
            if e.minute != last_min:
                last_min = e.minute
                for p in tr.active.values():
                    active_minutes[p.type] += 1
        team_minutes = 2 * m.duration_minutes
        for t in prof["window_activation_rate"]:
            rates[t].append(active_minutes[t] / team_minutes)
    return {"calibration_target": prof["target_rate"], "calibration_rate": prof["window_activation_rate"],
            "held_out_matches": [c["label"] for c in CURATED],
            "held_out_active_share": {t: round(float(np.mean(v)), 3) for t, v in rates.items()},
            "note": "share of team-minutes with the pattern active (hysteresis keeps patterns on for a while, so this is "
                    "higher than the per-window trigger rate)"}


# ---------------------------------------------------------------- C + D. xG and predictions on real matches
def brier(p, y):
    p, y = np.array(p), np.array(y)
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(np.array(p), 1e-4, 1 - 1e-4)
    y = np.array(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


async def eval_real(corpus) -> dict:
    """Next-action model on real matches. (xG and goal-threat are evaluated out-of-sample in eval/fit_models.py.)"""
    hits = major = n = 0
    for m, evs, _ in corpus:
        eng = TacticalEngine(m.match_id, m.home_team_id, m.away_team_id)
        prev = None
        for e in evs:
            if prev is not None and e.type.value in TRACKED and prev in TRACKED:
                row = {b: c for (a, b), c in eng.transitions_matrix.items() if a == prev and b in TRACKED}
                if row:  # predicted BEFORE the event is seen, from transitions observed so far in this match
                    n += 1
                    hits += int(max(row, key=row.get) == e.type.value)
                    major += int(e.type.value == "PASS")
            eng.update(e)
            prev = e.type.value
    return {"matches": len(corpus), "next_action": {"predictions": n, "top1_accuracy": round(hits / max(1, n), 3),
                                                     "always_pass_baseline": round(major / max(1, n), 3)}}


async def main():
    t0 = time.time()
    res = {"patterns_synthetic": eval_patterns()}
    print("A done", json.dumps(res["patterns_synthetic"], indent=1)[:1500])
    res["threshold_generalisation"] = await eval_generalisation()
    print("B done", res["threshold_generalisation"]["held_out_active_share"])
    corpus = await load_corpus()
    res["real_data"] = await eval_real(corpus)
    print("C/D done", json.dumps(res["real_data"], indent=1))
    res["runtime_s"] = round(time.time() - t0, 1)
    OUT.mkdir(exist_ok=True)
    (OUT / "deterministic.json").write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
