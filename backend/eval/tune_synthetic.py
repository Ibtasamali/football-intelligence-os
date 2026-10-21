"""Supervised threshold tuning for the synthetic profile (train seeds 0–29; evaluation uses held-out seeds 100–129).

Each 60-s team sample is labelled from the generator's tactical script (with a 2–4 min lag allowance, since the
features use 5–7 min windows). Thresholds maximise per-pattern F1 on the training samples.

  python -m eval.tune_synthetic   → app/tactical/profiles/synthetic.json
"""
from __future__ import annotations

import itertools
import json
from types import SimpleNamespace

import numpy as np

from eval.calibrate import sample_features
from eval.deterministic import ground_truth
from app.data.synthetic import MatchSimulator
from app.data.teams import AWAY_ID, HOME_ID
from app.tactical.patterns import PROFILE_DIR

GRIDS = {
    "HIGH_PRESS": (("press_ppda_max", np.arange(2.5, 7.01, 0.5)), ("press_opp_half_min", range(4, 15)),
                   ("press_defx_min", range(48, 65, 2))),
    "FLANK_OVERLOAD": (("flank_share_min", np.arange(0.45, 0.80, 0.025)), ("flank_actions_min", range(6, 24, 2))),
    "DEEP_BLOCK": (("block_line_max", np.arange(18, 28.01, 0.5)), ("block_drop_min", np.arange(1, 9.01, 0.5))),
    "TRANSITION_VULNERABILITY": (("trans_fast_min", (2, 3, 4)), ("trans_ratio_min", np.arange(1.0, 2.41, 0.2)),
                                 ("trans_line_min", range(26, 40, 2))),
}
PRED = {
    "HIGH_PRESS": lambda r, t: r.get("press_ppda") is not None and r["press_ppda"] <= t["press_ppda_max"]
    and r["press_opp_half"] >= t["press_opp_half_min"] and r["press_defx"] >= t["press_defx_min"],
    "FLANK_OVERLOAD": lambda r, t: r.get("flank_share") is not None and r["flank_share"] >= t["flank_share_min"]
    and r["flank_actions"] >= t["flank_actions_min"],
    "DEEP_BLOCK": lambda r, t: r.get("block_line") is not None and r["block_line"] <= t["block_line_max"]
    and r["block_drop"] >= t["block_drop_min"],
    "TRANSITION_VULNERABILITY": lambda r, t: r["trans_fast"] >= t["trans_fast_min"] and r["trans_ratio"] >= t["trans_ratio_min"]
    and r["trans_line"] >= t["trans_line_min"],
}


def main():
    gt = ground_truth()
    rows = []
    for seed in range(30):
        evs = MatchSimulator(f"tune-{seed}", seed).generate()
        rows += sample_features(SimpleNamespace(match_id=f"tune-{seed}", home_team_id=HOME_ID, away_team_id=AWAY_ID), evs)
    print(len(rows), "training samples")
    current = json.loads((PROFILE_DIR / "synthetic.json").read_text())["thresholds"] if (PROFILE_DIR / "synthetic.json").exists() else {}
    from app.tactical.patterns import DEFAULT_PROFILES
    th = dict(DEFAULT_PROFILES["synthetic"])
    report = {}
    for pattern, grid in GRIDS.items():
        labels = np.array([any(g["type"] == pattern and g["team"] == r["team"] and g["start"] + 2 <= r["t"] / 60 <= g["end"] + 4
                               for g in gt) for r in rows])
        best = None
        keys = [k for k, _ in grid]
        for combo in itertools.product(*[v for _, v in grid]):
            t = dict(zip(keys, (float(x) for x in combo)))
            pred = np.array([PRED[pattern](r, t) for r in rows])
            tp = int((pred & labels).sum())
            fp = int((pred & ~labels).sum())
            fn = int((~pred & labels).sum())
            f1 = 2 * tp / max(1, 2 * tp + fp + fn)
            if best is None or f1 > best[0]:
                best = (f1, t, tp, fp, fn)
        f1, t, tp, fp, fn = best
        th.update(t)
        report[pattern] = {"train_f1": round(f1, 3), "train_precision": round(tp / max(1, tp + fp), 3),
                           "train_recall": round(tp / max(1, tp + fn), 3), "thresholds": {k: round(v, 3) for k, v in t.items()}}
        print(pattern, report[pattern])
    (PROFILE_DIR / "synthetic.json").write_text(json.dumps({"thresholds": {k: round(v, 3) for k, v in th.items()},
                                                            "training": report, "train_seeds": "0–29",
                                                            "previous": current or DEFAULT_PROFILES["synthetic"]}, indent=2))


if __name__ == "__main__":
    main()
