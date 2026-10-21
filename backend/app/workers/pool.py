"""Agent worker pool: priority task queue + stateless workers + deduplication + load shedding.

One replica runs N asyncio workers. Horizontal scale = more replicas consuming a shared queue
(Azure Service Bus / Redis Streams); tasks carry everything they need (match_id, event_id, run_id),
so any worker can execute any task.
"""
from __future__ import annotations

import asyncio
import itertools
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.observability import OBS

log = get_logger("workers")


@dataclass(order=True)
class Task:
    priority: float
    seq: int
    key: str = field(compare=False)
    run: Callable[[], Awaitable[None]] = field(compare=False)
    created: float = field(default_factory=time.time, compare=False)
    max_age_s: float = field(default=30.0, compare=False)


class WorkerPool:
    def __init__(self, concurrency: int = 8, max_queue: int = 64) -> None:
        self.q: asyncio.PriorityQueue[Task] = asyncio.PriorityQueue()
        self.concurrency, self.max_queue = concurrency, max_queue
        self.workers: list[asyncio.Task] = []
        self.inflight: set[str] = set()
        self.recent: OrderedDict[str, float] = OrderedDict()
        self._seq = itertools.count()
        self.active = 0

    def start(self) -> None:
        if not self.workers:
            self.workers = [asyncio.create_task(self._worker(i)) for i in range(self.concurrency)]

    async def stop(self) -> None:
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []

    def submit(self, key: str, significance: float, run: Callable[[], Awaitable[None]], max_age_s: float = 30.0) -> bool:
        if key in self.inflight or key in self.recent:
            OBS.incr("tasks_deduplicated")
            return False
        if self.q.qsize() >= self.max_queue and significance < 0.6:
            OBS.incr("tasks_shed")
            return False
        self.inflight.add(key)
        self.q.put_nowait(Task(-significance, next(self._seq), key, run, max_age_s=max_age_s))
        OBS.incr("tasks_submitted")
        return True

    async def _worker(self, i: int) -> None:
        while True:
            task = await self.q.get()
            try:
                if time.time() - task.created > task.max_age_s and task.priority > -0.6:
                    OBS.incr("tasks_expired")
                    continue
                self.active += 1
                await task.run()
                OBS.incr("tasks_completed")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                OBS.incr("tasks_failed")
                log.exception("task_failed", key=task.key, error=str(exc)[:300])
            finally:
                self.active = max(0, self.active - 1)
                self.inflight.discard(task.key)
                self.recent[task.key] = time.time()
                while len(self.recent) > 5000:
                    self.recent.popitem(last=False)
                self.q.task_done()

    async def drain(self, timeout: float = 120) -> None:
        await asyncio.wait_for(self.q.join(), timeout)

    def status(self) -> dict:
        return {"workers": len(self.workers), "active": self.active, "queued": self.q.qsize(), "inflight": len(self.inflight)}
