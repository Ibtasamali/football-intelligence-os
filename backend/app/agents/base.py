"""Agent template. Agents are stateless; all state arrives in AgentContext and leaves in AgentResult."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from app.models.domain import AgentResult, MatchEvent
from app.services.observability import OBS
from app.services.tracing import span


@dataclass
class AgentContext:
    runtime: Any                      # MatchRuntime
    services: Any                     # Container
    state: dict                       # FootballState (read-only view)
    event: MatchEvent | None = None
    extras: dict = field(default_factory=dict)

    def result(self, name: str) -> dict:
        r = self.state.get("agent_results", {}).get(name)
        return r.get("output", {}) if r else {}


class Agent:
    name: str = "agent"
    family: str = "perception"
    uses_llm: bool = False
    description: str = ""

    async def execute(self, ctx: AgentContext) -> tuple[dict, float, list[str]]:
        raise NotImplementedError

    async def run(self, ctx: AgentContext) -> AgentResult:
        t0 = time.perf_counter()
        with span(f"agent {self.name}", match_id=ctx.runtime.match_id if ctx.runtime else None,
                  run_id=ctx.state.get("run_id"), agent_name=self.name, agent_family=self.family):
            try:
                output, confidence, evidence = await self.execute(ctx)
                status = output.pop("_status", "complete")
                res = AgentResult(agent=self.name, status=status, output=output, confidence=round(confidence, 3),
                                  evidence_event_ids=evidence, latency_ms=(time.perf_counter() - t0) * 1000,
                                  tokens=int(output.pop("_tokens", 0)), model=output.pop("_model", "deterministic"))
            except Exception as exc:  # noqa: BLE001 — a failing agent must not fail the graph
                res = AgentResult(agent=self.name, status="failed", error=f"{type(exc).__name__}: {exc}",
                                  latency_ms=(time.perf_counter() - t0) * 1000)
                res.output = {"trace": traceback.format_exc(limit=3)}
        OBS.record_agent(res, ctx.runtime.match_id if ctx.runtime else None)
        await ctx.services.publish_agent_status(ctx.runtime.match_id if ctx.runtime else None, res,
                                                ctx.state.get("run_id"))
        return res
