from app.prediction.models import goal_threat, next_action_distribution, predict, substitution_impact


def test_predictions_are_probabilities(played):
    eng, tracker, _ = played
    preds = predict(eng, "PASS", tracker.active_list())
    assert preds
    for p in preds:
        assert 0 <= p.probability <= 1
        assert p.kind == "prediction" and p.basis


def test_next_action_distribution(played):
    eng, _, _ = played
    dist = next_action_distribution(eng, "PASS", top=9)
    assert abs(sum(p for _, p in dist) - 1) < 0.01
    assert dist[0][0] == "PASS"


def test_goal_threat_is_fitted_and_calibrated_range(played):
    """Fitted on real matches (eval/fit_models.py): rare-event probabilities near the real base rate (~8%)."""
    eng, _, _ = played
    g = goal_threat(eng, "azc", [])
    assert "fitted" in g["model"] and 0.01 < g["p_goal_next_10"] < 0.4


def test_handset_fallback_still_uses_patterns(played):
    from app.prediction.models import _goal_threat_handset
    eng, _, _ = played
    pat = [{"type": "TRANSITION_VULNERABILITY", "team_id": "tha", "metrics": {}}]
    assert _goal_threat_handset(eng, "azc", pat)["p_goal_next_10"] > _goal_threat_handset(eng, "azc", [])["p_goal_next_10"]


def test_substitution_impact_windows(played):
    eng, _, _ = played
    imp = substitution_impact(eng, eng.substitutions[0])
    assert imp and set(imp) == {"before", "after", "window_minutes"}
