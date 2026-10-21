"""Model selection on VALIDATION seeds (30–59): per pattern, keep the hand-set or the supervised thresholds,
whichever gives the higher event-level F1. The test seeds (100–129) are never used for any choice.

  python -m eval.select_synthetic
"""
from __future__ import annotations

import json

import app.tactical.patterns as P
from eval.deterministic import eval_patterns

KEYS = {"HIGH_PRESS": ("press_",), "FLANK_OVERLOAD": ("flank_",), "DEEP_BLOCK": ("block_",),
        "TRANSITION_VULNERABILITY": ("trans_",), "MIDFIELD_SUPERIORITY": ("mid_",)}


def f1(d):
    p, r = d.get("precision") or 0, d.get("recall") or 0
    return 2 * p * r / (p + r) if p + r else 0


def run_with(th: dict) -> dict:
    orig = P.load_profile
    P.load_profile = lambda name: th if name == "synthetic" else orig(name)
    try:
        return eval_patterns(seeds=range(30, 60))["per_pattern"]
    finally:
        P.load_profile = orig


def main():
    f = P.PROFILE_DIR / "synthetic.json"
    prof = json.loads(f.read_text())
    hand, tuned = {**P.DEFAULT_PROFILES["synthetic"]}, prof["thresholds"]
    res_h, res_t = run_with(hand), run_with(tuned)
    final, choice = dict(hand), {}
    for pat, prefixes in KEYS.items():
        fh, ft = f1(res_h.get(pat, {})), f1(res_t.get(pat, {}))
        pick = "supervised" if ft > fh else "hand-set"
        choice[pat] = {"choice": pick, "val_f1_hand": round(fh, 3), "val_f1_supervised": round(ft, 3)}
        if pick == "supervised":
            final.update({k: v for k, v in tuned.items() if k.startswith(prefixes)})
    prof["thresholds"], prof["selection"] = final, {"validation_seeds": "30–59", **choice}
    f.write_text(json.dumps(prof, indent=2))
    print(json.dumps(choice, indent=1))


if __name__ == "__main__":
    main()
