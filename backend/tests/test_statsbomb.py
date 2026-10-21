"""StatsBomb adapter tests — run against the locally cached open-data files (skipped if not downloaded)."""
import pytest

from app.data.statsbomb import CACHE, load_match, team_frame
from app.tactical.patterns import load_profile

FINAL = CACHE / "events" / "3869685.json"
pytestmark = pytest.mark.skipif(not FINAL.exists(), reason="StatsBomb cache not present (run the app once online)")


def test_coordinate_transform():
    assert team_frame([120, 40]) == (105.0, 34.0)          # opponent goal centre
    tx, ty = team_frame([60, 80])                            # StatsBomb y=80 is the acting team's right touchline
    assert tx == 52.5 and ty == 0.0


async def test_world_cup_final_is_faithful():
    m, evs, info = await load_match(3869685, 43, 106, "t-final")
    goals = [e for e in evs if e.type.value == "GOAL"]
    assert [g.minute for g in goals] == [22, 35, 79, 80, 107, 117]
    assert goals[-1].meta["score"] == {m.home_team_id: 3, m.away_team_id: 3}
    assert m.notes["penalties"] == "Argentina win 4–2 on penalties"
    assert m.duration_minutes == 120 and not m.synthetic
    shots = [e for e in evs if e.type.value == "SHOT"]
    assert all(e.meta["xg_source"] == "statsbomb" for e in shots)
    assert info["positions_from_360_pct"] > 50
    for e in evs[:400]:
        if e.positions:
            assert len(e.positions) == 22
            assert all(0 <= p.x <= 105 and 0 <= p.y <= 68 for p in e.positions)


def test_calibrated_profile_differs_from_synthetic():
    real, synth = load_profile("statsbomb"), load_profile("synthetic")
    assert real != synth and real["press_ppda_max"] > synth["press_ppda_max"]
