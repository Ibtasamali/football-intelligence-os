"""StatsBomb Open Data adapter — real matches into the Football Intelligence OS event schema.

Data: https://github.com/statsbomb/open-data (free for non-commercial use; attribution required:
"Data provided by StatsBomb"). Files are downloaded once and cached under backend/data_cache/statsbomb.

Conversion
- Coordinates: StatsBomb uses a 120 × 80 pitch, each event seen from the acting team attacking left→right
  with y = 0 at the top (the team's LEFT touchline). We convert to our 105 × 68 absolute frame where the
  home team attacks towards x = 105 and, in team frame, y = 0 is the team's RIGHT touchline.
- Event types are mapped to our vocabulary; shots keep StatsBomb's own xG (`statsbomb_xg`).
- Positions: where a StatsBomb 360 freeze frame exists, visible players are matched to the on-pitch
  players (actor exact, keeper exact, others by nearest expected slot). Players outside the camera view use a
  formation-slot model that follows the ball. Each event records how many positions are real (`positions_360`).
- Clocks keep StatsBomb's real match minutes (45' restarts the second half, 90'/105' start extra time).
"""
from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import httpx

from app.core.config import BACKEND_DIR
from app.core.logging import get_logger
from app.data.teams import register_player, register_team
from app.models.domain import EventType, Match, MatchEvent, Player, PlayerPosition, Team

log = get_logger("statsbomb")

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = BACKEND_DIR / "data_cache" / "statsbomb"
L, W = 105.0, 68.0
ATTRIBUTION = "Data provided by StatsBomb (open data, non-commercial use)"

CURATED = [
    {"key": "wc2022-final", "sb_match_id": 3869685, "competition_id": 43, "season_id": 106,
     "label": "FIFA World Cup 2022 Final — Argentina vs France"},
    {"key": "euro2024-final", "sb_match_id": 3943043, "competition_id": 55, "season_id": 282,
     "label": "UEFA Euro 2024 Final — Spain vs England"},
    {"key": "wc2022-sf-arg-cro", "sb_match_id": 3869519, "competition_id": 43, "season_id": 106,
     "label": "FIFA World Cup 2022 Semi-final — Argentina vs Croatia"},
]

KIT = {  # primary kit colours for well-known national teams (fallback palette otherwise)
    "Argentina": "#75AADB", "France": "#1E3A8A", "Spain": "#C60B1E", "England": "#E2E8F0", "Croatia": "#E11D48",
    "Morocco": "#B91C1C", "Netherlands": "#F97316", "Germany": "#F8FAFC", "Portugal": "#991B1B", "Brazil": "#FACC15",
    "Belgium": "#DC2626", "Italy": "#2563EB", "Turkey": "#EF4444", "Switzerland": "#DC2626",
}
PALETTE = ["#3BA4F6", "#F2555A", "#34D399", "#FACC15"]

# StatsBomb position name → (our code, team-frame slot x, y). y = 0 is the team's right touchline.
POS = {
    "Goalkeeper": ("GK", 5, 34), "Right Back": ("RB", 32, 8), "Right Wing Back": ("RB", 40, 6),
    "Right Center Back": ("CB", 26, 23), "Center Back": ("CB", 25, 34), "Left Center Back": ("CB", 26, 45),
    "Left Back": ("LB", 32, 60), "Left Wing Back": ("LB", 40, 62),
    "Right Defensive Midfield": ("DM", 41, 26), "Center Defensive Midfield": ("DM", 41, 34),
    "Left Defensive Midfield": ("DM", 41, 42), "Right Midfield": ("RW", 55, 9), "Right Center Midfield": ("CM", 51, 24),
    "Center Midfield": ("CM", 51, 34), "Left Center Midfield": ("CM", 51, 44), "Left Midfield": ("LW", 55, 59),
    "Right Wing": ("RW", 70, 9), "Right Attacking Midfield": ("AM", 63, 25), "Center Attacking Midfield": ("AM", 63, 34),
    "Left Attacking Midfield": ("AM", 63, 43), "Left Wing": ("LW", 70, 59), "Right Center Forward": ("ST", 76, 27),
    "Center Forward": ("ST", 78, 34), "Left Center Forward": ("ST", 76, 41), "Secondary Striker": ("ST", 70, 34),
}

SHOT_OUTCOME = {"Goal": "goal", "Saved": "saved", "Saved To Post": "saved", "Saved Off Target": "saved",
                "Blocked": "blocked", "Off T": "off_target", "Wayward": "off_target", "Post": "off_target"}


# ---------------------------------------------------------------- download + cache
async def fetch(path: str, client: httpx.AsyncClient | None = None):
    target = CACHE / path
    if target.exists():
        return json.loads(target.read_text())
    own = client is None
    client = client or httpx.AsyncClient(timeout=90)
    try:
        for attempt in range(4):
            try:
                r = await client.get(f"{BASE_URL}/{path}")
                if r.status_code == 404:
                    r.raise_for_status()
                r.raise_for_status()
                data = r.json()
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".part")
                tmp.write_bytes(r.content)
                tmp.replace(target)  # atomic: a partial download is never cached
                return data
            except (httpx.TransportError, json.JSONDecodeError):
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)
    finally:
        if own:
            await client.aclose()


async def fetch_optional(path: str, client=None):
    try:
        return await fetch(path, client)
    except httpx.HTTPStatusError:
        return None


# ---------------------------------------------------------------- geometry
def team_frame(loc) -> tuple[float, float]:
    """StatsBomb [x, y] (acting team attacking right) → our team frame (tx, ty)."""
    x, y = loc[0], loc[1]
    return x * L / 120.0, (80.0 - y) * W / 80.0


def to_abs(team_id: str, home_id: str, tx: float, ty: float) -> tuple[float, float]:
    return (tx, ty) if team_id == home_id else (L - tx, W - ty)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def sb_formation(n) -> str:
    return "-".join(str(n)) if n else "unknown"


# ---------------------------------------------------------------- converter
class Converter:
    def __init__(self, match_id: str, meta: dict, lineups: list, events: list, frames: list | None) -> None:
        self.match_id = match_id
        self.meta = meta
        h, a = meta["home_team"], meta["away_team"]
        self.home = f"sb{h['home_team_id']}"
        self.away = f"sb{a['away_team_id']}"
        self.team_of = {h["home_team_id"]: self.home, a["away_team_id"]: self.away}
        self.names = {h["home_team_id"]: h["home_team_name"], a["away_team_id"]: a["away_team_name"]}
        self.frames = {f["event_uuid"]: f for f in (frames or [])}
        self.lineups = lineups
        self.events = sorted(events, key=lambda e: e["index"])
        self.by_uuid = {e["id"]: e for e in self.events}
        self.slot: dict[str, tuple[float, float]] = {}       # player → current formation slot (team frame)
        self.code: dict[str, str] = {}
        self.on_pitch: dict[str, list[str]] = {self.home: [], self.away: []}
        self.out: list[MatchEvent] = []
        self.score = {self.home: 0, self.away: 0}
        self.seq = 0
        self.teams: dict[str, Team] = {}

    # ------------------------------------------------------------ registry
    def register(self) -> None:
        managers = {}
        for side in ("home_team", "away_team"):
            t = self.meta[side]
            mg = (t.get("managers") or [{}])[0]
            managers[t[f"{side}_id"]] = mg.get("nickname") or mg.get("name") or "unknown"
        formations = {e["team"]["id"]: sb_formation(e["tactics"]["formation"]) for e in self.events if e["type"]["name"] == "Starting XI"}
        for i, (sbid, tid) in enumerate(self.team_of.items()):
            name = self.names[sbid]
            color = KIT.get(name, PALETTE[i])
            if i == 1 and color.lower() == KIT.get(self.names[list(self.team_of)[0]], "").lower():
                color = PALETTE[1]
            team = Team(team_id=tid, name=name, short_name=name[:3].upper(), colors={"primary": color, "secondary": "#ffffff"},
                        formation=formations.get(sbid, "unknown"), style="", coach=managers.get(sbid, "unknown"))
            register_team(team)
            self.teams[tid] = team
        for team_lineup in self.lineups:
            tid = self.team_of[team_lineup["team_id"]]
            for p in team_lineup["lineup"]:
                pid = f"sbp{p['player_id']}"
                first_pos = (p.get("positions") or [{}])[0].get("position", "Center Midfield")
                code, sx, sy = POS.get(first_pos, ("CM", 51, 34))
                started = any(pp.get("start_reason") == "Starting XI" for pp in p.get("positions", []))
                register_player(Player(player_id=pid, team_id=tid, name=p.get("player_nickname") or p["player_name"],
                                       number=p.get("jersey_number") or 0, position=code, role=first_pos,
                                       bench=not started), (sx, sy))

    def set_lineup(self, sb_team_id: int, lineup: list) -> None:
        tid = self.team_of[sb_team_id]
        self.on_pitch[tid] = []
        for p in lineup:
            pid = f"sbp{p['player']['id']}"
            code, sx, sy = POS.get(p["position"]["name"], ("CM", 51, 34))
            self.slot[pid], self.code[pid] = (sx, sy), code
            self.on_pitch[tid].append(pid)

    # ------------------------------------------------------------ positions
    def model_positions(self, poss_team: str, ball_abs: tuple[float, float]) -> dict[str, tuple[float, float]]:
        """Formation-slot model following the ball (used where 360 data does not see a player)."""
        out = {}
        for tid, players in self.on_pitch.items():
            in_poss = tid == poss_team
            bx_, by_ = ball_abs if tid == self.home else (L - ball_abs[0], W - ball_abs[1])
            for pid in players:
                sx, sy = self.slot.get(pid, (50, 34))
                if self.code.get(pid) == "GK":
                    tx, ty = 5 + max(0.0, bx_ - 55) * 0.15, 34 + (by_ - 34) * 0.15
                elif in_poss:
                    tx, ty = sx * 0.78 + bx_ * 0.38 - 6, 34 + (sy - 34) * 1.1
                else:
                    tx, ty = 30 + (sx - 27) * 0.72 + (bx_ - 52) * 0.3, by_ + (sy - by_) * 0.62
                out[pid] = to_abs(tid, self.home, clamp(tx, 1.5, 103.5), clamp(ty, 1.5, 66.5))
        return out

    def positions_for(self, e: dict, team: str, ball_abs: tuple[float, float]) -> tuple[list[PlayerPosition], int]:
        pos = self.model_positions(team, ball_abs)
        frame = self.frames.get(e["id"])
        real = 0
        if frame and team:
            opp = self.away if team == self.home else self.home
            actor = f"sbp{e['player']['id']}" if e.get("player") else None
            taken: set[str] = set()
            pts = []
            for f in frame.get("freeze_frame", []):
                tx, ty = team_frame(f["location"])
                side = team if f["teammate"] else opp
                ax, ay = to_abs(team, self.home, tx, ty)
                pts.append((side, ax, ay, f.get("actor"), f.get("keeper")))
            # actor and keepers first, then greedy nearest-slot matching
            for side, ax, ay, is_actor, is_keeper in pts:
                pid = None
                if is_actor and actor in self.on_pitch.get(side, []):
                    pid = actor
                elif is_keeper:
                    pid = next((p for p in self.on_pitch[side] if self.code.get(p) == "GK"), None)
                if pid and pid not in taken:
                    pos[pid] = (ax, ay)
                    taken.add(pid)
                    real += 1
            pairs = []
            for i, (side, ax, ay, is_actor, is_keeper) in enumerate(pts):
                if is_actor or is_keeper:
                    continue
                for pid in self.on_pitch[side]:
                    if pid in taken or self.code.get(pid) == "GK":
                        continue
                    mx, my = pos[pid]
                    pairs.append((math.hypot(mx - ax, my - ay), i, pid))
            used_pts: set[int] = set()
            for d, i, pid in sorted(pairs):
                if i in used_pts or pid in taken:
                    continue
                _, ax, ay, _, _ = pts[i]
                pos[pid] = (ax, ay)
                taken.add(pid)
                used_pts.add(i)
                real += 1
        out = [PlayerPosition(player_id=pid, team_id=tid, x=round(clamp(pos[pid][0], 0, L), 2), y=round(clamp(pos[pid][1], 0, W), 2))
               for tid, players in self.on_pitch.items() for pid in players if pid in pos]
        return out, real

    # ------------------------------------------------------------ emit
    def emit(self, e: dict, etype: EventType, *, team: str | None, player: str | None, loc=None, end=None,
             outcome: str | None = None, related: str | None = None, poss: str | None = None, **meta) -> MatchEvent:
        x = y = ex = ey = None
        if loc is not None and team:
            x, y = to_abs(team, self.home, *team_frame(loc))
        if end is not None and team:
            ex, ey = to_abs(team, self.home, *team_frame(end))
        ball = (ex, ey) if ex is not None else ((x, y) if x is not None else (52.5, 34.0))
        poss_team = poss or team or self.home
        positions, real = self.positions_for(e, poss_team if e.get("team") is None else team, ball) if team else ([], 0)
        ev = MatchEvent(event_id=f"{self.match_id}-e{self.seq:05d}", match_id=self.match_id, seq=self.seq,
                        minute=e["minute"], second=e["second"], type=etype, team_id=team, player_id=player,
                        x=None if x is None else round(x, 2), y=None if y is None else round(y, 2),
                        end_x=None if ex is None else round(ex, 2), end_y=None if ey is None else round(ey, 2),
                        outcome=outcome, related_player_id=related,
                        meta={**meta, "period": e["period"], "sb_event": e["id"], "positions_360": real},
                        positions=positions)
        self.out.append(ev)
        self.seq += 1
        return ev

    def convert(self) -> list[MatchEvent]:
        E = EventType
        half_time_done = False
        last_possession_team = None
        shootout = []
        for e in self.events:
            t = e["type"]["name"]
            if e["period"] == 5:
                if t == "Shot":
                    shootout.append((self.team_of[e["team"]["id"]], e["shot"]["outcome"]["name"] == "Goal"))
                continue
            team = self.team_of.get(e.get("team", {}).get("id"))
            player = f"sbp{e['player']['id']}" if e.get("player") else None
            loc = e.get("location")
            if t in ("Starting XI", "Tactical Shift"):
                self.set_lineup(e["team"]["id"], e["tactics"]["lineup"])
                continue
            if t == "Pass":
                p = e["pass"]
                ptype = p.get("type", {}).get("name")
                if ptype == "Corner":
                    self.emit(e, E.CORNER, team=team, player=player, loc=loc, end=p.get("end_location"), outcome="taken")
                fail = "outcome" in p
                self.emit(e, E.PASS, team=team, player=player, loc=loc, end=p.get("end_location"),
                          outcome="fail" if fail else "success",
                          related=f"sbp{p['recipient']['id']}" if p.get("recipient") else None,
                          cross=bool(p.get("cross")), under_pressure=bool(e.get("under_pressure")),
                          goal_assist=bool(p.get("goal_assist")), set_piece=ptype)
                if fail and p["outcome"]["name"] == "Pass Offside":
                    self.emit(e, E.OFFSIDE, team=team, player=player, loc=p.get("end_location"), outcome="offside")
            elif t == "Carry":
                self.emit(e, E.CARRY, team=team, player=player, loc=loc, end=e["carry"].get("end_location"), outcome="success")
            elif t == "Shot":
                s = e["shot"]
                outcome = SHOT_OUTCOME.get(s["outcome"]["name"], "off_target")
                assist = None
                if s.get("key_pass_id") and s["key_pass_id"] in self.by_uuid:
                    kp = self.by_uuid[s["key_pass_id"]]
                    assist = f"sbp{kp['player']['id']}" if kp.get("player") else None
                xg = round(float(s.get("statsbomb_xg", 0.0)), 3)
                self.emit(e, E.SHOT, team=team, player=player, loc=loc, end=s.get("end_location", [120, 40])[:2],
                          outcome=outcome, related=assist, xg=xg, header=s.get("body_part", {}).get("name") == "Head",
                          big_chance=xg >= 0.3, penalty=s.get("type", {}).get("name") == "Penalty", xg_source="statsbomb")
                if outcome == "goal":
                    self.score[team] += 1
                    self.emit(e, E.GOAL, team=team, player=player, loc=loc, outcome="goal", related=assist, xg=xg,
                              score=dict(self.score), penalty=s.get("type", {}).get("name") == "Penalty")
            elif t == "Own Goal For":
                self.score[team] += 1
                self.emit(e, E.GOAL, team=team, player=None, loc=loc, outcome="goal", own_goal=True, score=dict(self.score))
            elif t == "Pressure":
                self.emit(e, E.PRESSURE, team=team, player=player, loc=loc)
            elif t == "Ball Recovery":
                if not e.get("ball_recovery", {}).get("recovery_failure"):
                    self.emit(e, E.RECOVERY, team=team, player=player, loc=loc, outcome="success")
            elif t == "Interception":
                ok = e["interception"]["outcome"]["name"] in ("Won", "Success In Play", "Success To Team")
                self.emit(e, E.INTERCEPTION, team=team, player=player, loc=loc, outcome="success" if ok else "fail")
                if ok:
                    self.emit(e, E.RECOVERY, team=team, player=player, loc=loc, outcome="success")
            elif t == "Duel" and e["duel"]["type"]["name"] == "Tackle":
                ok = e["duel"].get("outcome", {}).get("name") in ("Won", "Success", "Success In Play", "Success Out")
                self.emit(e, E.TACKLE, team=team, player=player, loc=loc, outcome="success" if ok else "fail")
                if ok:
                    self.emit(e, E.RECOVERY, team=team, player=player, loc=loc, outcome="success")
            elif t == "Foul Committed":
                self.emit(e, E.FOUL, team=team, player=player, loc=loc)
                card = e.get("foul_committed", {}).get("card", {}).get("name")
                if card:
                    self.emit(e, E.CARD, team=team, player=player, loc=loc, outcome="yellow" if card == "Yellow Card" else "red")
            elif t == "Bad Behaviour" and e.get("bad_behaviour", {}).get("card"):
                card = e["bad_behaviour"]["card"]["name"]
                self.emit(e, E.CARD, team=team, player=player, loc=loc, outcome="yellow" if card == "Yellow Card" else "red")
            elif t == "Substitution":
                rep = f"sbp{e['substitution']['replacement']['id']}"
                if player in self.on_pitch[team]:
                    i = self.on_pitch[team].index(player)
                    self.on_pitch[team][i] = rep
                    self.slot[rep], self.code[rep] = self.slot.get(player, (50, 34)), self.code.get(player, "CM")
                self.emit(e, E.SUBSTITUTION, team=team, player=rep, related=player,
                          reason=e["substitution"].get("outcome", {}).get("name", "").lower())
            elif t == "Goal Keeper" and e["goalkeeper"]["type"]["name"] in ("Shot Saved", "Shot Saved To Post", "Penalty Saved"):
                self.emit(e, E.SAVE, team=team, player=player, loc=loc, outcome="success")
            elif t == "Half End" and e["period"] == 1 and not half_time_done and team == self.home:
                half_time_done = True
                self.emit(e, E.HALF_TIME, team=None, player=None, score=dict(self.score))
            if team and e.get("possession_team") and t in ("Ball Recovery", "Interception", "Duel"):
                pt = self.team_of.get(e["possession_team"]["id"])
                if last_possession_team and pt != last_possession_team and self.out and self.out[-1].type == E.RECOVERY:
                    self.emit(e, E.POSSESSION_CHANGE, team=pt, player=player, loc=loc, from_team=last_possession_team)
                last_possession_team = pt
            elif e.get("possession_team"):
                last_possession_team = self.team_of.get(e["possession_team"]["id"])
        last = self.events[-1]
        pens = None
        if shootout:
            made = {self.home: sum(1 for t, g in shootout if t == self.home and g),
                    self.away: sum(1 for t, g in shootout if t == self.away and g)}
            winner = max(made, key=made.get)
            pens = {"home": made[self.home], "away": made[self.away], "winner": winner,
                    "text": f"{self.teams[winner].name} win {max(made.values())}–{min(made.values())} on penalties"}
        fake = {**last, "period": min(4, last["period"])}
        self.emit(fake, E.FULL_TIME, team=None, player=None, score=dict(self.score), penalties=pens)
        self.penalties = pens
        return self.out


# ---------------------------------------------------------------- public API
async def load_match(sb_match_id: int, competition_id: int, season_id: int, match_id: str):
    """Return (Match, events, info) for a StatsBomb match, registering its teams and players."""
    async with httpx.AsyncClient(timeout=90) as client:
        matches, events, lineups, frames = await asyncio.gather(
            fetch(f"matches/{competition_id}/{season_id}.json", client), fetch(f"events/{sb_match_id}.json", client),
            fetch(f"lineups/{sb_match_id}.json", client), fetch_optional(f"three-sixty/{sb_match_id}.json", client))
    meta = next(m for m in matches if m["match_id"] == sb_match_id)
    conv = Converter(match_id, meta, lineups, events, frames)
    conv.register()
    evs = conv.convert()
    duration = 120 if any(e.get("period", 0) >= 3 for e in events) else 90
    comp = f"{meta['competition']['competition_name']} {meta['season']['season_name']} · {meta['competition_stage']['name']}"
    notes = {"attribution": ATTRIBUTION, "sb_match_id": sb_match_id, "competition_id": competition_id,
             "season_id": season_id, "match_date": meta["match_date"],
             "final_score": f"{meta['home_score']}–{meta['away_score']}", "has_360": bool(frames)}
    if conv.penalties:
        notes["penalties"] = conv.penalties["text"]
    match = Match(match_id=match_id, home_team_id=conv.home, away_team_id=conv.away, competition=comp,
                  venue=(meta.get("stadium") or {}).get("name", "unknown"), kickoff=f"{meta['match_date']}T{meta.get('kick_off', '00:00')}",
                  synthetic=False, source="statsbomb", duration_minutes=duration, notes=notes,
                  score={conv.home: 0, conv.away: 0})
    real = sum(e.meta.get("positions_360", 0) for e in evs)
    total = sum(len(e.positions) for e in evs) or 1
    info = {"events": len(evs), "positions_from_360_pct": round(100 * real / total, 1), "teams": [conv.home, conv.away],
            "meta": meta}
    log.info("statsbomb_loaded", match=match_id, events=len(evs), real_positions_pct=info["positions_from_360_pct"])
    return match, evs, info


async def team_history(meta: dict, competition_id: int, season_id: int, limit: int = 6) -> list[dict]:
    """Earlier matches in the same competition for both teams (for the real historical archive)."""
    matches = await fetch(f"matches/{competition_id}/{season_id}.json")
    date = meta["match_date"]
    ids = {meta["home_team"]["home_team_id"], meta["away_team"]["away_team_id"]}
    out = []
    for team_id in ids:
        prior = [m for m in matches if m["match_date"] < date and team_id in (m["home_team"]["home_team_id"], m["away_team"]["away_team_id"])]
        out += sorted(prior, key=lambda m: m["match_date"])[-limit:]
    uniq = {m["match_id"]: m for m in out}
    return sorted(uniq.values(), key=lambda m: m["match_date"])
