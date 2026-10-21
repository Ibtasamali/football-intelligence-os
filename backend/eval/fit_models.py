"""Fit the probabilistic models on REAL matches with a match-level train/test split.

- Goal threat: logistic regression for P(team scores in the next 10 minutes) from live features.
- xG: logistic regression on distance, visible goal angle and header (non-penalty shots).

Matches are split deterministically (every 4th match → test). Coefficients are written to
app/prediction/fitted.json and used at runtime; test-set metrics go to eval/results/fitted.json.

  python -m eval.fit_models
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from eval.corpus import load_corpus
from app.prediction.models import goal_features
from app.tactical.engine import TacticalEngine
from app.tactical.patterns import PatternTracker
from app.tactical.xg import shot_geometry

ROOT = Path(__file__).resolve().parents[1]


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> np.ndarray:
    """Newton/IRLS with L2 (intercept unpenalised). X already includes a leading 1-column."""
    w = np.zeros(X.shape[1])
    reg = np.eye(X.shape[1]) * l2
    reg[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + reg @ w
        H = (X * (p * (1 - p))[:, None]).T @ X + reg
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def auc(p, y):
    o = np.argsort(p)
    r = np.empty(len(p))
    r[o] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def predict(X, w):
    return 1 / (1 + np.exp(-X @ w))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def collect(corpus):
    goal_rows, shot_rows = [], []
    for m, evs, label in corpus:
        goals = defaultdict(list)
        for e in evs:
            if e.type.value == "GOAL":
                goals[e.team_id].append((e.meta.get("period"), e.game_seconds))
        eng = TacticalEngine(m.match_id, m.home_team_id, m.away_team_id)
        tr = PatternTracker("statsbomb")
        next_t = 300
        for e in evs:
            if e.type.value == "SHOT" and not e.meta.get("penalty") and e.x is not None and e.team_id in eng.stats:
                tx, ty = eng.tf(e)
                d, a = shot_geometry(tx, ty)
                shot_rows.append((m.match_id, [d, a, float(bool(e.meta.get("header")))], int(e.outcome == "goal"),
                                  float(e.meta.get("xg", 0)), (tx, ty, bool(e.meta.get("header")))))
            eng.update(e)
            tr.update(eng)
            if e.game_seconds >= next_t and e.meta.get("period", 1) <= 4:
                next_t = e.game_seconds + 60
                for tid in (eng.home, eng.away):
                    f = goal_features(eng, tid, tr.active_list())
                    per = e.meta.get("period")
                    y = int(any(gp == per and 0 < gt - e.game_seconds <= 600 for gp, gt in goals[tid]))
                    goal_rows.append((m.match_id, f, y))
    return goal_rows, shot_rows


async def main():
    corpus = await load_corpus()
    ids = sorted({m.match_id for m, _, _ in corpus})
    test_ids = set(ids[::4])
    goal_rows, shot_rows = collect(corpus)

    def split(rows, n_feat_idx=1):
        tr = [r for r in rows if r[0] not in test_ids]
        te = [r for r in rows if r[0] in test_ids]
        return tr, te

    # ---- goal threat: grouped 5-fold CV over all matches (features chosen by CV; see docs/EVALUATION.md)
    names = ["xg_10", "shots_10"]
    def gx(rows):
        return np.array([[1.0] + [r[1][k] for k in names] for r in rows]), np.array([r[2] for r in rows], float)
    folds = [set(ids[i::5]) for i in range(5)]
    P_, Y_, B_ = [], [], []
    for f in folds:
        Xtr, ytr = gx([r for r in goal_rows if r[0] not in f])
        Xte, yte = gx([r for r in goal_rows if r[0] in f])
        mu_f, sd_f = Xtr[:, 1:].mean(0), Xtr[:, 1:].std(0) + 1e-9
        nf = lambda X: np.hstack([X[:, :1], (X[:, 1:] - mu_f) / sd_f])  # noqa: E731
        wf = fit_logistic(nf(Xtr), ytr, l2=20.0)
        P_ += list(predict(nf(Xte), wf)); Y_ += list(yte); B_ += [ytr.mean()] * len(yte)
    P_, Y_, B_ = map(np.array, (P_, Y_, B_))
    bins = []
    for lo, hi in zip([0, 0.06, 0.08, 0.1, 0.13], [0.06, 0.08, 0.1, 0.13, 1.01]):
        idx = (P_ >= lo) & (P_ < hi)
        if idx.sum():
            bins.append({"bin": f"{lo:.2f}–{min(hi, 1):.2f}", "n": int(idx.sum()), "mean_predicted": round(float(P_[idx].mean()), 3),
                         "observed_rate": round(float(Y_[idx].mean()), 3)})
    Xall, yall = gx(goal_rows)
    mu, sd = Xall[:, 1:].mean(0), Xall[:, 1:].std(0) + 1e-9
    w = fit_logistic(np.hstack([Xall[:, :1], (Xall[:, 1:] - mu) / sd]), yall, l2=20.0)
    goal_res = {"features": names, "samples": len(goal_rows), "positives": int(yall.sum()), "validation": "grouped 5-fold CV by match",
                "brier_model": round(brier(P_, Y_), 5), "brier_constant": round(brier(B_, Y_), 5),
                "logloss_model": round(logloss(P_, Y_), 4), "logloss_constant": round(logloss(B_, Y_), 4),
                "auc": round(auc(P_, Y_), 3), "reliability": bins,
                "coefficients_standardised": {n: round(float(c), 3) for n, c in zip(["intercept"] + names, w)}}
    goal_res["brier_skill_score"] = round(1 - goal_res["brier_model"] / goal_res["brier_constant"], 4)

    # ---- xG
    def sx(rows):
        X = np.array([[1.0, r[1][0], r[1][1], r[1][2]] for r in rows])
        return X, np.array([r[2] for r in rows], float), np.array([r[3] for r in rows])
    str_, ste = split(shot_rows)
    Xs, ys, _ = sx(str_)
    Xt, yt, sbt = sx(ste)
    wx = fit_logistic(Xs, ys, l2=0.5)
    px = predict(Xt, wx)
    from app.tactical.xg import expected_goals
    old = np.array([expected_goals(r[4][0], r[4][1], header=r[4][2], fitted=False) for r in ste])
    xg_res = {"train_shots": len(str_), "test_shots": len(ste), "test_goals": int(yt.sum()),
              "brier_fitted": round(brier(px, yt), 4), "brier_previous_handset": round(brier(old, yt), 4),
              "brier_statsbomb": round(brier(sbt, yt), 4), "brier_constant": round(brier(np.full(len(yt), ys.mean()), yt), 4),
              "logloss_fitted": round(logloss(px, yt), 4), "logloss_statsbomb": round(logloss(sbt, yt), 4),
              "pearson_r_vs_statsbomb": round(float(np.corrcoef(px, sbt)[0, 1]), 3),
              "mean_fitted": round(float(px.mean()), 3), "observed_rate": round(float(yt.mean()), 3),
              "coefficients": {"intercept": round(float(wx[0]), 4), "distance": round(float(wx[1]), 4),
                               "angle": round(float(wx[2]), 4), "header": round(float(wx[3]), 4)}}

    fitted = {"goal_threat": {"features": names, "mean": mu.tolist(), "std": sd.tolist(), "weights": w.tolist(),
                              "cv_auc": goal_res["auc"], "cv_brier_skill": goal_res["brier_skill_score"]},
              "xg": xg_res["coefficients"],
              "trained_on": f"{len(ids) - len(test_ids)} real matches (StatsBomb Open Data), {len(test_ids)} held out"}
    (ROOT / "app/prediction/fitted.json").write_text(json.dumps(fitted, indent=2))
    (ROOT / "eval/results/fitted.json").write_text(json.dumps({"goal_threat": goal_res, "xg": xg_res,
                                                               "test_matches": sorted(test_ids)}, indent=2))
    print(json.dumps({"goal_threat": goal_res, "xg": xg_res}, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
