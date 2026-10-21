"""Deterministic synthetic match generator.

Produces a full 90-minute event stream with 22-player position snapshots on every event.
Team behaviour is driven by a *tactical script* (press intensity, block height, flank bias, tempo)
so that the tactical engine has genuine patterns to discover — the engine is never told about
the script; it must detect the patterns from the events and positions alone.

Story of the demo match (Azure City FC vs Thames Athletic):
  15'–25'  Azure City switch on an aggressive high press
  25'–40'  Thames overload the right flank through their overlapping right-back
  34'      Thames score from a right-side cross (0–1)
  46'      Azure City sub: a direct left winger — attack shifts to the left
  55'–65'  Azure City press intensifies; 61' press-driven goal (1–1)
  66'–76'  Thames drop into a deep block
  76'+     Thames chase a winner, push full-backs high → transition vulnerability
  83'      Azure City counter-attack goal (2–1)
  88'      Thames' biggest chance, saved
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from app.data.teams import AWAY_ID, BASE_SHAPE, HOME_ID, PLAYERS, STARTING_XI, opponent
from app.models.domain import EventType, MatchEvent, PlayerPosition
from app.tactical.xg import expected_goals

L, W = 105.0, 68.0


@dataclass
class Phase:
    start: int
    end: int
    press: float = 0.45      # 0..1 how aggressively the team presses out of possession
    block: float = 30.0      # defensive line height (m from own goal) out of possession
    flank: float = 0.0       # +1 = attacks down own right, -1 = own left
    directness: float = 0.4  # 0..1
    fb_push: float = 0.0     # extra metres full-backs push up in possession


SCRIPT: dict[str, list[Phase]] = {
    HOME_ID: [
        Phase(0, 15, press=0.5, block=33),
        Phase(15, 25, press=0.9, block=42, directness=0.45),
        Phase(25, 46, press=0.5, block=32),
        Phase(46, 55, press=0.6, block=34, flank=-0.75, directness=0.55),
        Phase(55, 66, press=0.93, block=43, flank=-0.6, directness=0.5),
        Phase(66, 76, press=0.55, block=36, flank=-0.3),
        Phase(76, 95, press=0.45, block=28, directness=0.8),
    ],
    AWAY_ID: [
        Phase(0, 25, press=0.4, block=30),
        Phase(25, 41, press=0.4, block=30, flank=0.9, fb_push=20, directness=0.5),
        Phase(41, 66, press=0.4, block=29, flank=0.4, fb_push=8),
        Phase(66, 76, press=0.25, block=17, directness=0.7),
        Phase(76, 95, press=0.72, block=40, flank=0.2, fb_push=24, directness=0.6),
    ],
}


def phase_for(team_id: str, minute: int) -> Phase:
    for ph in SCRIPT[team_id]:
        if ph.start <= minute < ph.end:
            return ph
    return SCRIPT[team_id][-1]


def to_abs(team_id: str, tx: float, ty: float) -> tuple[float, float]:
    return (tx, ty) if team_id == HOME_ID else (L - tx, W - ty)


def to_team(team_id: str, x: float, y: float) -> tuple[float, float]:
    return (x, y) if team_id == HOME_ID else (L - x, W - y)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class MatchSimulator:
    def __init__(self, match_id: str, seed: int = 11) -> None:
        self.match_id = match_id
        self.rng = random.Random(seed)
        self.t = 0.0
        self.seq = 0
        self.events: list[MatchEvent] = []
        self.on_pitch = {HOME_ID: list(STARTING_XI[HOME_ID]), AWAY_ID: list(STARTING_XI[AWAY_ID])}
        self.score = {HOME_ID: 0, AWAY_ID: 0}
        self.second_half = False
        self.beats = self._beats()

    # ------------------------------------------------------------------ positions
    @property
    def minute(self) -> int:
        return int(self.t // 60)

    def _shape(self, team_id: str, in_possession: bool, ball_abs: tuple[float, float]) -> list[PlayerPosition]:
        ph = phase_for(team_id, self.minute)
        btx, bty = to_team(team_id, *ball_abs)
        out = []
        for pid in self.on_pitch[team_id]:
            bx, by = BASE_SHAPE[pid]
            pos = PLAYERS[pid].position
            if pos == "GK":
                tx = 5 + (max(0.0, btx - 50) * 0.18 if in_possession else max(0.0, btx - 70) * 0.1)
                ty = 34 + (bty - 34) * 0.15
            elif in_possession:
                tx = bx * 0.78 + btx * 0.38 - 6
                if pos in ("RB", "LB"):
                    side_bias = ph.flank if pos == "RB" else -ph.flank
                    tx += ph.fb_push * max(0.2, side_bias)
                ty = 34 + (by - 34) * 1.12
                ty += -ph.flank * 6 if pos not in ("CB", "GK") else 0
            else:
                tx = ph.block + (bx - 27) * (0.62 + 0.25 * (1 - ph.press)) + (btx - 52) * (0.18 + 0.2 * ph.press)
                if ph.press > 0.8 and pos in ("ST", "RW", "LW", "AM", "CM"):
                    tx += 6
                ty = bty + (by - bty) * 0.62
            tx += self.rng.uniform(-1.4, 1.4)
            ty += self.rng.uniform(-1.4, 1.4)
            out.append(PlayerPosition(player_id=pid, team_id=team_id, x=0, y=0))
            out[-1].x, out[-1].y = (round(v, 2) for v in to_abs(team_id, clamp(tx, 1.5, 103.5), clamp(ty, 1.5, 66.5)))
        return out

    def _positions(self, possession_team: str | None, ball_abs: tuple[float, float]) -> list[PlayerPosition]:
        if possession_team is None:
            possession_team = HOME_ID
        return (self._shape(possession_team, True, ball_abs)
                + self._shape(opponent(possession_team), False, ball_abs))

    def _nearest(self, team_id: str, tx: float, ty: float, exclude: set[str] | None = None,
                 positions: list[PlayerPosition] | None = None, allow_gk: bool = False) -> str:
        exclude = exclude or set()
        positions = positions or self._positions(team_id, to_abs(team_id, tx, ty))
        x, y = to_abs(team_id, tx, ty)
        best, best_d = None, 1e9
        for p in positions:
            if p.team_id != team_id or p.player_id in exclude:
                continue
            if PLAYERS[p.player_id].position == "GK" and not allow_gk:
                continue
            d = math.hypot(p.x - x, p.y - y)
            if d < best_d:
                best, best_d = p.player_id, d
        return best or self.on_pitch[team_id][1]

    # ------------------------------------------------------------------ emit
    def _emit(self, etype: EventType, team_id: str | None, player_id: str | None, tx: float | None = None,
              ty: float | None = None, etx: float | None = None, ety: float | None = None, *,
              outcome: str | None = None, related: str | None = None, dt: float = 3.0,
              possession: str | None = None, **meta) -> MatchEvent:
        x = y = ex = ey = None
        if tx is not None and team_id:
            x, y = to_abs(team_id, tx, ty)
        if etx is not None and team_id:
            ex, ey = to_abs(team_id, etx, ety)
        ball = (ex, ey) if ex is not None else ((x, y) if x is not None else (52.5, 34.0))
        ev = MatchEvent(
            event_id=f"{self.match_id}-e{self.seq:05d}", match_id=self.match_id, seq=self.seq, minute=self.minute, second=int(self.t % 60), type=etype,
            team_id=team_id, player_id=player_id,
            x=None if x is None else round(x, 2), y=None if y is None else round(y, 2),
            end_x=None if ex is None else round(ex, 2), end_y=None if ey is None else round(ey, 2),
            outcome=outcome, related_player_id=related, meta=meta,
            positions=self._positions(possession or team_id, ball),
        )
        self.events.append(ev)
        self.seq += 1
        self.t += dt
        return ev

    def _shot(self, team_id: str, shooter: str, tx: float, ty: float, *, header=False, big=False,
              outcome: str | None = None, assist: str | None = None) -> str:
        xg = expected_goals(tx, ty, header=header, big_chance=big)
        if outcome is None:
            r = self.rng.random()
            outcome = "off_target" if r < 0.42 else "blocked" if r < 0.68 else "saved"
        self._emit(EventType.SHOT, team_id, shooter, tx, ty, 105, 34 + self.rng.uniform(-3, 3),
                   outcome=outcome, related=assist, dt=2, xg=xg, header=header, big_chance=big)
        opp = opponent(team_id)
        if outcome == "goal":
            self.score[team_id] += 1
            self._emit(EventType.GOAL, team_id, shooter, tx, ty, outcome="goal", related=assist, dt=55,
                       xg=xg, score=dict(self.score))
            self._emit(EventType.KICK_OFF, opp, self.on_pitch[opp][9], 52.5, 34, dt=2)
            return opp
        if outcome == "saved":
            gk = self.on_pitch[opp][0]
            self._emit(EventType.SAVE, opp, gk, 103 - tx + 2, 68 - ty, outcome="success", dt=3, possession=opp)
            if self.rng.random() < 0.4:
                return self._corner(team_id)
            return opp
        if outcome == "blocked" and self.rng.random() < 0.45:
            return self._corner(team_id)
        return opp

    def _corner(self, team_id: str) -> str:
        side = self.rng.choice([1.0, 67.0])
        taker = self._nearest(team_id, 100, side)
        self._emit(EventType.CORNER, team_id, taker, 104.5, side, 96, 34, outcome="taken", dt=25)
        if self.rng.random() < 0.3:
            target = self._nearest(team_id, 96, 34, exclude={taker})
            return self._shot(team_id, target, 96 + self.rng.uniform(-2, 2), 34 + self.rng.uniform(-5, 5), header=True)
        opp = opponent(team_id)
        clearer = self._nearest(opp, 12, 34)
        self._emit(EventType.INTERCEPTION, opp, clearer, 10, 34, outcome="success", dt=2)
        return opp

    def _turnover(self, lost_team: str, tx: float, ty: float, pressured: bool) -> str:
        opp = opponent(lost_team)
        otx, oty = L - tx, W - ty
        winner = self._nearest(opp, otx, oty)
        etype = EventType.INTERCEPTION if self.rng.random() < 0.55 else EventType.TACKLE
        self._emit(etype, opp, winner, otx, oty, outcome="success", dt=1, possession=opp, pressured=pressured)
        self._emit(EventType.RECOVERY, opp, winner, otx, oty, outcome="success", dt=1, possession=opp)
        self._emit(EventType.POSSESSION_CHANGE, opp, winner, otx, oty, dt=0.5, possession=opp, from_team=lost_team)
        return opp

    # ------------------------------------------------------------------ open-play sequence
    def _sequence(self, team_id: str, tx: float, ty: float, carrier: str | None = None) -> str:
        ph, oph = phase_for(team_id, self.minute), phase_for(opponent(team_id), self.minute)
        carrier = carrier or self._nearest(team_id, tx, ty)
        n_passes = self.rng.randint(3, 10) if ph.directness < 0.6 else self.rng.randint(2, 6)
        opp = opponent(team_id)
        for _ in range(n_passes):
            pressured = False
            press_zone = tx < 45 or (oph.press > 0.85 and tx < 60)
            if press_zone and self.rng.random() < oph.press * 0.75:
                presser = self._nearest(opp, L - tx, W - ty)
                self._emit(EventType.PRESSURE, opp, presser, L - tx, W - ty, dt=1, possession=team_id,
                           target=carrier)
                pressured = True
            fwd = self.rng.gauss(6 + 12 * ph.directness, 8)
            etx = clamp(tx + fwd, 3, 101)
            ety = clamp(self.rng.gauss(34 - ph.flank * 22, 13), 2, 66)
            receiver = self._nearest(team_id, etx, ety, exclude={carrier})
            p_success = 0.93 - 0.32 * (etx / L) ** 2 - (0.24 * oph.press if pressured else 0) - max(0, fwd - 15) * 0.008
            if self.rng.random() < 0.025 and etx > 75 and fwd > 18:
                self._emit(EventType.OFFSIDE, team_id, receiver, etx, ety, outcome="offside", dt=20)
                return opp
            if self.rng.random() < p_success:
                self._emit(EventType.PASS, team_id, carrier, tx, ty, etx, ety, outcome="success", related=receiver,
                           dt=self.rng.uniform(2, 5), under_pressure=pressured)
                tx, ty, carrier = etx, ety, receiver
                if self.rng.random() < 0.22:
                    ctx_, cty = clamp(tx + self.rng.uniform(4, 13), 3, 101), clamp(ty + self.rng.uniform(-5, 5), 2, 66)
                    self._emit(EventType.CARRY, team_id, carrier, tx, ty, ctx_, cty, outcome="success", dt=3)
                    tx, ty = ctx_, cty
            else:
                self._emit(EventType.PASS, team_id, carrier, tx, ty, etx, ety, outcome="fail", related=receiver,
                           dt=1.5, under_pressure=pressured)
                if self.rng.random() < 0.06:
                    fouler = self._nearest(opp, L - etx, W - ety)
                    self._emit(EventType.FOUL, opp, fouler, L - etx, W - ety, related=receiver, dt=25, possession=team_id)
                    return team_id
                return self._turnover(team_id, etx, ety, pressured)
            if tx > 82 and self.rng.random() < 0.15:
                return self._shot(team_id, carrier, min(tx, self.rng.uniform(76, 92)), ty)
        if tx > 76 and self.rng.random() < 0.1:
            return self._shot(team_id, carrier, min(tx, self.rng.uniform(74, 88)), ty)
        return self._turnover(team_id, tx, ty, False)

    # ------------------------------------------------------------------ scripted beats
    def _beats(self):
        H, A = HOME_ID, AWAY_ID
        E = EventType

        def press_chance():  # 19' AZC high press forces a turnover → shot
            self._emit(E.PASS, A, "tha_5", 14, 24, 30, 30, outcome="success", related="tha_4", dt=2)
            self._emit(E.PRESSURE, H, "azc_9", 75, 38, dt=1, possession=A, target="tha_4")
            self._emit(E.PASS, A, "tha_4", 30, 30, 38, 22, outcome="fail", related="tha_7", dt=1, under_pressure=True)
            self._emit(E.INTERCEPTION, H, "azc_10", 67, 46, outcome="success", dt=1, pressured=True)
            self._emit(E.RECOVERY, H, "azc_10", 67, 46, outcome="success", dt=1)
            self._emit(E.POSSESSION_CHANGE, H, "azc_10", 67, 46, dt=0.5, from_team=A)
            self._emit(E.PASS, H, "azc_10", 69, 44, 87, 37, outcome="success", related="azc_9", dt=2)
            return self._shot(H, "azc_9", 88, 36, outcome="saved", assist="azc_10")

        def mensah_cross_blocked():
            self._emit(E.PASS, A, "tha_7", 66, 14, 82, 5, outcome="success", related="tha_2", dt=3)
            self._emit(E.CARRY, A, "tha_2", 82, 5, 90, 6, outcome="success", dt=3)
            self._emit(E.PASS, A, "tha_2", 90, 6, 96, 32, outcome="fail", related="tha_9", dt=1, cross=True)
            return self._corner(A)

        def tha_goal():  # 34' right-flank overload → cross → header
            self._emit(E.PASS, A, "tha_8", 44, 40, 60, 22, outcome="success", related="tha_10", dt=3)
            self._emit(E.PASS, A, "tha_10", 60, 22, 67, 13, outcome="success", related="tha_7", dt=3)
            self._emit(E.PASS, A, "tha_7", 67, 13, 84, 5, outcome="success", related="tha_2", dt=2, overlap=True)
            self._emit(E.CARRY, A, "tha_2", 84, 5, 91, 7, outcome="success", dt=3)
            self._emit(E.PASS, A, "tha_2", 91, 7, 95, 31, outcome="success", related="tha_9", dt=1, cross=True)
            return self._shot(A, "tha_9", 95, 31, header=True, big=True, outcome="goal", assist="tha_2")

        def sub_kessler():
            self.on_pitch[H][self.on_pitch[H].index("azc_11")] = "azc_17"
            self._emit(E.SUBSTITUTION, H, "azc_17", related="azc_11", dt=30, reason="tactical: direct left winger")
            return A

        def sow_card():
            self._emit(E.FOUL, A, "tha_4", 50, 30, related="azc_10", dt=10, possession=H, stopped_counter=True)
            self._emit(E.CARD, A, "tha_4", 50, 30, outcome="yellow", dt=40, possession=H)
            return H

        def press_chance_2():
            self._emit(E.PASS, A, "tha_6", 18, 44, 30, 52, outcome="success", related="tha_3", dt=2)
            self._emit(E.PRESSURE, H, "azc_17", 76, 15, dt=1, possession=A, target="tha_3")
            self._emit(E.PASS, A, "tha_3", 30, 52, 40, 40, outcome="fail", related="tha_8", dt=1, under_pressure=True)
            self._emit(E.TACKLE, H, "azc_8", 66, 28, outcome="success", dt=1, pressured=True)
            self._emit(E.RECOVERY, H, "azc_8", 66, 28, outcome="success", dt=1)
            self._emit(E.POSSESSION_CHANGE, H, "azc_8", 66, 28, dt=0.5, from_team=A)
            self._emit(E.PASS, H, "azc_8", 66, 28, 84, 52, outcome="success", related="azc_17", dt=2)
            return self._shot(H, "azc_17", 86, 50, outcome="off_target", assist="azc_8")

        def azc_goal_press():  # 61' press-driven equaliser
            self._emit(E.PASS, A, "tha_6", 15, 40, 28, 38, outcome="success", related="tha_8", dt=2)
            self._emit(E.PRESSURE, H, "azc_8", 77, 30, dt=1, possession=A, target="tha_8")
            self._emit(E.PRESSURE, H, "azc_9", 82, 36, dt=0.5, possession=A, target="tha_8")
            self._emit(E.PASS, A, "tha_8", 28, 38, 33, 24, outcome="fail", related="tha_4", dt=1, under_pressure=True)
            self._emit(E.INTERCEPTION, H, "azc_10", 72, 44, outcome="success", dt=1, pressured=True)
            self._emit(E.RECOVERY, H, "azc_10", 72, 44, outcome="success", dt=1)
            self._emit(E.POSSESSION_CHANGE, H, "azc_10", 72, 44, dt=0.5, from_team=A)
            self._emit(E.PASS, H, "azc_10", 74, 44, 87, 55, outcome="success", related="azc_17", dt=2)
            self._emit(E.CARRY, H, "azc_17", 87, 55, 94, 47, outcome="success", dt=2)
            self._emit(E.PASS, H, "azc_17", 94, 47, 93, 36, outcome="success", related="azc_9", dt=1, cutback=True)
            return self._shot(H, "azc_9", 93, 36, big=True, outcome="goal", assist="azc_17")

        def sub_reyes():
            self.on_pitch[A][self.on_pitch[A].index("tha_10")] = "tha_15"
            self._emit(E.SUBSTITUTION, A, "tha_15", related="tha_10", dt=30, reason="defensive: protect the draw")
            return H

        def sub_pierce():
            self.on_pitch[A][self.on_pitch[A].index("tha_8")] = "tha_19"
            self._emit(E.SUBSTITUTION, A, "tha_19", related="tha_8", dt=30, reason="attacking: chase the winner")
            return A

        def counter_1():  # 79' transition chance
            self._emit(E.PASS, A, "tha_2", 80, 8, 92, 30, outcome="fail", related="tha_19", dt=1, cross=True)
            self._emit(E.INTERCEPTION, H, "azc_6", 14, 38, outcome="success", dt=1)
            self._emit(E.RECOVERY, H, "azc_6", 14, 38, outcome="success", dt=1)
            self._emit(E.POSSESSION_CHANGE, H, "azc_6", 14, 38, dt=0.5, from_team=A)
            self._emit(E.PASS, H, "azc_6", 16, 38, 45, 30, outcome="success", related="azc_10", dt=2)
            self._emit(E.PASS, H, "azc_10", 45, 30, 70, 10, outcome="success", related="azc_7", dt=2, long_ball=True)
            self._emit(E.CARRY, H, "azc_7", 70, 10, 85, 20, outcome="success", dt=3)
            return self._shot(H, "azc_7", 86, 22, outcome="saved")

        def azc_goal_counter():  # 83' counter-attack winner
            self._emit(E.PASS, A, "tha_3", 78, 62, 90, 40, outcome="fail", related="tha_19", dt=1, cross=True)
            self._emit(E.INTERCEPTION, H, "azc_4", 13, 26, outcome="success", dt=1)
            self._emit(E.RECOVERY, H, "azc_4", 13, 26, outcome="success", dt=1)
            self._emit(E.POSSESSION_CHANGE, H, "azc_4", 13, 26, dt=0.5, from_team=A)
            self._emit(E.PASS, H, "azc_4", 14, 26, 40, 32, outcome="success", related="azc_10", dt=2)
            self._emit(E.PASS, H, "azc_10", 40, 32, 68, 9, outcome="success", related="azc_7", dt=2, long_ball=True)
            self._emit(E.CARRY, H, "azc_7", 68, 9, 88, 24, outcome="success", dt=4)
            return self._shot(H, "azc_7", 89, 25, big=True, outcome="goal")

        def tha_big_miss():  # 88'
            self._emit(E.PASS, A, "tha_3", 84, 60, 96, 34, outcome="success", related="tha_19", dt=2, cross=True)
            return self._shot(A, "tha_19", 97, 34, big=True, outcome="saved", assist="tha_3")

        return [
            (19 * 60 + 5, A, press_chance), (29 * 60 + 40, A, mensah_cross_blocked), (34 * 60 + 10, A, tha_goal),
            (45 * 60 + 1, None, sub_kessler), (52 * 60 + 30, H, sow_card), (58 * 60 + 20, A, press_chance_2),
            (61 * 60 + 5, A, azc_goal_press), (66 * 60 + 0, None, sub_reyes), (76 * 60 + 30, None, sub_pierce),
            (79 * 60 + 10, A, counter_1), (83 * 60 + 15, A, azc_goal_counter), (88 * 60 + 30, A, tha_big_miss),
        ]

    # ------------------------------------------------------------------ main loop
    def generate(self) -> list[MatchEvent]:
        E = EventType
        self._emit(E.KICK_OFF, HOME_ID, "azc_9", 52.5, 34, dt=1)
        team, tx, ty = HOME_ID, 50.0, 34.0
        beat_i = 0
        while True:
            if not self.second_half and self.t >= 45 * 60:
                self.t = 45 * 60
                self._emit(E.HALF_TIME, None, None, dt=0, score=dict(self.score))
                self.second_half = True
                self.t = 45 * 60 + 0.5
                if beat_i < len(self.beats) and self.beats[beat_i][1] is None and self.beats[beat_i][0] <= self.t:
                    self.beats[beat_i][2]()
                    beat_i += 1
                self._emit(E.KICK_OFF, AWAY_ID, "tha_9", 52.5, 34, dt=1)
                team, tx, ty = AWAY_ID, 50.0, 34.0
            if self.t >= 90 * 60 + 90:
                break
            if beat_i < len(self.beats) and self.t >= self.beats[beat_i][0]:
                _, _, fn = self.beats[beat_i]
                beat_i += 1
                team = fn()
                tx, ty = 25.0, 34.0
                continue
            team = self._sequence(team, tx, ty)
            last = self.events[-1]
            if last.x is not None and last.team_id == team:
                tx, ty = to_team(team, last.x, last.y)
            else:
                tx, ty = (20.0, 34.0)
        self.t = min(self.t, 90 * 60 + 95)
        self._emit(E.FULL_TIME, None, None, dt=0, score=dict(self.score))
        return self.events


def generate_demo_match(match_id: str = "demo-azc-tha", seed: int = 11) -> list[MatchEvent]:
    return MatchSimulator(match_id, seed).generate()
