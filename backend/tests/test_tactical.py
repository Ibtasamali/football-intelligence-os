from app.tactical.xg import expected_goals


def test_xg_monotonic_with_distance():
    assert expected_goals(99, 34) > expected_goals(94, 34) > expected_goals(80, 34)
    assert 0.15 < expected_goals(94, 34) < 0.35          # penalty-spot range
    assert expected_goals(95, 31, header=True) < expected_goals(95, 31)


def test_final_score_and_totals(played):
    eng, _, _ = played
    assert eng.score == {"azc": 2, "tha": 1}
    tot = eng.totals()
    for t in ("azc", "tha"):
        assert 0 < tot[t]["pass_completion"] < 1
        assert 0.3 < tot[t]["possession"] < 0.7
        assert tot[t]["ppda"] is not None
    assert abs(tot["azc"]["possession"] + tot["tha"]["possession"] - 1) < 0.01
    # Azure City's scripted pressing identity must show up in the numbers
    assert tot["azc"]["ppda"] < tot["tha"]["ppda"]
    assert tot["azc"]["high_turnovers"] > tot["tha"]["high_turnovers"]


def _first(starts, ptype, team, lo, hi):
    return [m for m, t, tm, _ in starts if t == ptype and tm == team and lo <= m <= hi]


def test_patterns_detected_from_data_alone(played):
    _, _, starts = played
    assert _first(starts, "HIGH_PRESS", "azc", 15, 25), "AZC high press (15'–25') not detected"
    assert _first(starts, "FLANK_OVERLOAD", "tha", 25, 41), "THA right-flank overload not detected"
    assert _first(starts, "HIGH_PRESS", "azc", 55, 66), "AZC second-half press not detected"
    assert _first(starts, "DEEP_BLOCK", "tha", 66, 78), "THA deep block not detected"
    assert _first(starts, "TRANSITION_VULNERABILITY", "tha", 76, 83), "THA late transition risk not flagged before 83' goal"


def test_flank_overload_names_the_fullback(played):
    _, _, starts = played
    overloads = [p for m, t, tm, p in starts if t == "FLANK_OVERLOAD" and tm == "tha"]
    assert any("right" in p.zone for p in overloads)


def test_pattern_evidence_points_to_real_events(played):
    eng, tracker, _ = played
    for h in tracker.history:
        assert all(eid in eng.by_id for eid in h["evidence_event_ids"])


def test_passing_network_and_influence(played):
    eng, _, _ = played
    net = eng.passing_network("azc", 5)
    assert net and net[0]["count"] >= net[-1]["count"]
    top = eng.player_influence(top=3)
    assert len(top) == 3 and top[0]["influence"] >= top[1]["influence"]
