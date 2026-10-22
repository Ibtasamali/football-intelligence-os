"""Live replay of an event feed into the real-time pipeline.

Director mode varies speed so the 5-minute demo lingers on key moments without the system
knowing what is coming: speeds are keyed only to clock time, the AI still has to find the story.
"""
from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.models.domain import MatchEvent

log = get_logger("replay")

# (from minute, game-seconds per real second)
DIRECTOR = [(0, 60), (15, 14), (21, 60), (27, 16), (36, 60), (44, 40), (51, 30), (56, 14), (63, 50), (68, 18),
            (72, 50), (79, 12), (85, 40), (87.5, 12), (90, 40)]


class ReplayController:
    def __init__(self, container, match_id: str, events: list[MatchEvent], speed: float = 20.0, director: bool = True,
                 slow_windows: list[tuple[int, int]] | None = None) -> None:
        self.c, self.match_id, self.events = container, match_id, events
        self.speed, self.director = speed, director
        self.slow_windows = slow_windows  # real matches: broadcast-style pacing around big moments
        self.idx = 0
        self.running = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.finished = False

    def current_speed(self) -> float:
        if not self.director or self.idx >= len(self.events):
            return self.speed
        if self.slow_windows is not None:
            t = self.events[self.idx].game_seconds
            return 10 if any(a <= t <= b for a, b in self.slow_windows) else 55
        m = self.events[self.idx].game_seconds / 60
        sp = DIRECTOR[0][1]
        for start, s in DIRECTOR:
            if m >= start:
                sp = s
        return sp

    def start(self) -> None:
        self.running.set()
        if not self.task:
            self.task = asyncio.create_task(self._loop())

    def pause(self) -> None:
        self.running.clear()

    def stop(self) -> None:
        if self.task:
            self.task.cancel()
            self.task = None

    async def _loop(self) -> None:
        prev_t = self.events[self.idx].game_seconds if self.idx < len(self.events) else 0
        try:
            while self.idx < len(self.events):
                await self.running.wait()
                ev = self.events[self.idx]
                dt = max(0, ev.game_seconds - prev_t)
                if dt:
                    await asyncio.sleep(min(dt / self.current_speed(), 2.5))
                prev_t = ev.game_seconds
                await self.c.ingest(ev)
                self.idx += 1
            self.finished = True
            await self.c.broadcast(self.match_id, {"type": "replay_finished"})
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("replay_failed", match_id=self.match_id)

    async def jump_to(self, minute: float | None = None, seq: int | None = None) -> int:
        """Fast-forward through the fast path only (no LLM) up to `minute` or event index `seq`."""
        was_running = self.running.is_set()
        self.pause()
        n = 0
        def before(i: int) -> bool:
            return i < seq if seq is not None else self.events[i].game_seconds < (minute or 0) * 60
        while self.idx < len(self.events) and before(self.idx):
            await self.c.ingest(self.events[self.idx], deep=False)
            self.idx += 1
            n += 1
        await self.c.broadcast(self.match_id, {"type": "jumped", "minute": minute, "events": n})
        if was_running:
            self.running.set()
        return n

    def status(self) -> dict:
        cur = self.events[min(self.idx, len(self.events) - 1)] if self.events else None
        return {"match_id": self.match_id, "index": self.idx, "total": len(self.events), "running": self.running.is_set(),
                "speed": self.current_speed(), "director": self.director, "finished": self.finished,
                "clock": cur.clock if cur else "00:00"}


SYNTHETIC_JUMPS = [{"minute": 0, "label": "Kick-off"}, {"minute": 15, "label": "15' press era"},
                   {"minute": 26, "label": "26' flank overload"}, {"minute": 44, "label": "Half-time"},
                   {"minute": 56, "label": "56' second press"}, {"minute": 67, "label": "67' deep block"},
                   {"minute": 78, "label": "78' late drama"}]  # minute-based (synthetic clocks are monotonic)
