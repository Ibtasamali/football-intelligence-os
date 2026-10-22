"""Expected goals: a transparent distance/angle logistic model.

Feature form follows the classic public xG literature (distance to goal centre + visible goal-mouth
angle, with a header penalty). Coefficients are hand-calibrated so a penalty-spot shot ≈ 0.25–0.3 and
a 25 m shot ≈ 0.03–0.05. It is labelled in the UI as a model estimate, not ground truth.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_FITTED = Path(__file__).resolve().parents[1] / "prediction" / "fitted.json"
_COEF = json.loads(_FITTED.read_text()).get("xg") if _FITTED.exists() else None

GOAL_WIDTH = 7.32
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


def shot_geometry(tx: float, ty: float) -> tuple[float, float]:
    """tx/ty in the shooting team's frame (attacking towards x=105). Returns (distance m, angle rad)."""
    dx = PITCH_LENGTH - tx
    dy = abs(ty - PITCH_WIDTH / 2)
    distance = math.hypot(dx, dy)
    half = GOAL_WIDTH / 2
    angle = math.atan2(GOAL_WIDTH * dx, dx * dx + dy * dy - half * half)
    if angle < 0:
        angle += math.pi
    return distance, angle


def expected_goals(tx: float, ty: float, header: bool = False, big_chance: bool = False, fitted: bool = True) -> float:
    """Uses the logistic coefficients in app/prediction/fitted.json (estimated offline; only the parameters ship,
    no match data); otherwise the hand-set defaults below. `big_chance` is only used by the synthetic generator."""
    distance, angle = shot_geometry(tx, ty)
    if fitted and _COEF:
        c = _COEF
        logit = c["intercept"] + c["distance"] * distance + c["angle"] * angle + (c["header"] if header else 0.0)
    else:
        logit = -1.15 - 0.10 * distance + 1.55 * angle - (0.9 if header else 0.0)
    logit += 1.1 if big_chance else 0.0
    return round(1 / (1 + math.exp(-logit)), 3)
