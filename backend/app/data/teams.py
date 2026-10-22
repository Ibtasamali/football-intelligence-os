"""Fictional clubs used by the synthetic dataset (no real-world facts are implied)."""
from __future__ import annotations

from app.models.domain import Player, Team

HOME_ID = "azc"
AWAY_ID = "tha"

TEAMS = {
    HOME_ID: Team(team_id=HOME_ID, name="Azure City FC", short_name="AZC",
                  colors={"primary": "#3BA4F6", "secondary": "#E8F4FF"}, formation="4-3-3",
                  style="possession, aggressive high press", coach="Marta Varga"),
    AWAY_ID: Team(team_id=AWAY_ID, name="Thames Athletic", short_name="THA",
                  colors={"primary": "#F2555A", "secondary": "#FFF1F1"}, formation="4-2-3-1",
                  style="compact mid-block, fast right-sided attacks", coach="Ray Okafor"),
}

# (number, name, position, team-frame base x, base y). Team frame: x from own goal (0..105),
# y=0 is the team's RIGHT touchline when facing the opponent goal.
_AZC = [
    (1, "Jonas Ekström", "GK", 5, 34), (2, "Mateo Ruiz", "RB", 33, 8), (4, "Daniel Okoye", "CB", 27, 24),
    (5, "Luca Ferri", "CB", 27, 44), (3, "Sam Whitaker", "LB", 33, 60), (6, "Yusuf Demir", "DM", 44, 34),
    (8, "Elias Brandt", "CM", 54, 22), (10, "Kai Moreno", "CM", 54, 46), (7, "Theo Laurent", "RW", 72, 9),
    (9, "Marcus Hale", "ST", 78, 34), (11, "Rafael Costa", "LW", 72, 59),
]
_AZC_BENCH = [(17, "Noah Kessler", "LW", 72, 59), (14, "Arjun Mehta", "CM", 54, 22)]

_THA = [
    (1, "Oliver Grant", "GK", 5, 34), (2, "Kofi Mensah", "RB", 32, 8), (5, "Harry Vance", "CB", 26, 25),
    (6, "Mikel Etxeberria", "CB", 26, 43), (3, "Callum Price", "LB", 31, 60), (4, "Ibrahim Sow", "DM", 42, 27),
    (8, "Jack Holloway", "DM", 42, 41), (7, "Leon Adeyemi", "RW", 64, 11), (10, "Felix Novak", "AM", 63, 34),
    (11, "Dario Conti", "LW", 64, 57), (9, "Ethan Brooks", "ST", 76, 34),
]
_THA_BENCH = [(15, "Tomás Reyes", "DM", 42, 34), (19, "Jamal Pierce", "ST", 76, 34)]

ROLES = {
    "azc_10": "deep-lying playmaker", "azc_9": "pressing centre-forward", "azc_6": "ball-winning anchor",
    "tha_2": "overlapping attacking full-back", "tha_9": "aerial target striker", "tha_10": "creative 10",
    "azc_17": "direct inverted winger", "tha_19": "penalty-box finisher",
}


def _build(team_id: str, rows, bench=False) -> list[Player]:
    return [Player(player_id=f"{team_id}_{n}", team_id=team_id, name=name, number=n, position=pos,
                   role=ROLES.get(f"{team_id}_{n}", ""), bench=bench) for n, name, pos, _, _ in rows]


PLAYERS: dict[str, Player] = {p.player_id: p for p in
                              _build(HOME_ID, _AZC) + _build(HOME_ID, _AZC_BENCH, True)
                              + _build(AWAY_ID, _THA) + _build(AWAY_ID, _THA_BENCH, True)}

BASE_SHAPE: dict[str, tuple[float, float]] = {
    f"{tid}_{n}": (x, y) for tid, rows in ((HOME_ID, _AZC + _AZC_BENCH), (AWAY_ID, _THA + _THA_BENCH))
    for n, _, _, x, y in rows
}

STARTING_XI = {HOME_ID: [f"{HOME_ID}_{r[0]}" for r in _AZC], AWAY_ID: [f"{AWAY_ID}_{r[0]}" for r in _THA]}


def player_name(player_id: str | None) -> str:
    if not player_id:
        return "unknown"
    p = PLAYERS.get(player_id)
    return p.name if p else player_id


def team_name(team_id: str | None) -> str:
    t = TEAMS.get(team_id or "")
    return t.name if t else (team_id or "unknown")


def opponent(team_id: str) -> str:
    return AWAY_ID if team_id == HOME_ID else HOME_ID


def register_team(team: Team) -> None:
    """Add a team from an external data source (e.g. a live provider feed) to the shared registry."""
    TEAMS[team.team_id] = team


def register_player(player: Player, base: tuple[float, float] = (50.0, 34.0)) -> None:
    PLAYERS[player.player_id] = player
    BASE_SHAPE[player.player_id] = base
