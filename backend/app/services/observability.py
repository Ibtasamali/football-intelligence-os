"""Agent observability: per-agent latency/token/confidence stats, cache hit rates, cost avoided.

In Azure this is mirrored to Application Insights via OpenTelemetry; the in-process view powers the
Agent Control Center screen.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.models.domain import AgentResult


@dataclass
class AgentStats:
    runs: int = 0
    failures: int = 0
    cached: int = 0
    skipped: int = 0
    total_latency_ms: float = 0.0
    tokens: int = 0
    confidence_sum: float = 0.0
    last_status: str = "idle"
    last_latency_ms: float = 0.0
    last_confidence: float = 0.0
    last_evidence: int = 0
    last_model: str = "none"
    last_run_at: float = 0.0

    def as_dict(self, name: str) -> dict:
        done = max(1, self.runs - self.skipped)
        return {"agent": name, "runs": self.runs, "failures": self.failures, "cached": self.cached,
                "avg_latency_ms": round(self.total_latency_ms / done, 1), "tokens": self.tokens,
                "avg_confidence": round(self.confidence_sum / done, 3), "last_status": self.last_status,
                "last_latency_ms": round(self.last_latency_ms, 1), "last_confidence": round(self.last_confidence, 3),
                "last_evidence": self.last_evidence, "last_model": self.last_model, "last_run_at": self.last_run_at}


@dataclass
class Observability:
    agents: dict[str, AgentStats] = field(default_factory=lambda: defaultdict(AgentStats))
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    recent_runs: deque = field(default_factory=lambda: deque(maxlen=300))
    model_usage: dict[str, dict] = field(default_factory=lambda: defaultdict(lambda: {"calls": 0, "tokens": 0, "latency_ms": 0.0}))
    started_at: float = field(default_factory=time.time)

    def record_agent(self, r: AgentResult, match_id: str | None = None) -> None:
        s = self.agents[r.agent]
        s.runs += 1
        s.last_status = r.status
        s.last_run_at = time.time()
        if r.status == "failed":
            s.failures += 1
        elif r.status == "cached":
            s.cached += 1
        elif r.status == "skipped":
            s.skipped += 1
        s.total_latency_ms += r.latency_ms
        s.last_latency_ms = r.latency_ms
        s.tokens += r.tokens
        s.confidence_sum += r.confidence
        s.last_confidence = r.confidence
        s.last_evidence = len(r.evidence_event_ids)
        s.last_model = r.model
        self.counters["agent_runs"] += 1
        self.recent_runs.append({"agent": r.agent, "agent_run_id": r.agent_run_id, "status": r.status,
                                 "latency_ms": round(r.latency_ms, 1), "confidence": round(r.confidence, 3),
                                 "tokens": r.tokens, "model": r.model, "evidence": len(r.evidence_event_ids),
                                 "match_id": match_id, "at": time.time()})

    def record_llm(self, model: str, tokens: int, latency_ms: float, cached: bool) -> None:
        if cached:
            self.counters["llm_cache_hits"] += 1
            self.counters["tokens_saved"] += tokens
            return
        u = self.model_usage[model]
        u["calls"] += 1
        u["tokens"] += tokens
        u["latency_ms"] += latency_ms
        self.counters["llm_calls"] += 1
        self.counters["tokens_used"] += tokens

    def incr(self, key: str, by: float = 1) -> None:
        self.counters[key] += by

    def summary(self) -> dict:
        c = self.counters
        events = c.get("events_ingested", 0)
        analysed = c.get("events_analysed", 0)
        return {
            "uptime_s": round(time.time() - self.started_at),
            "counters": {k: round(v, 2) for k, v in c.items()},
            "events_without_llm_pct": round(100 * (1 - c.get("llm_calls", 0) / events), 1) if events else 100.0,
            "deep_analysis_pct": round(100 * analysed / events, 1) if events else 0.0,
            "agents": sorted((s.as_dict(n) for n, s in self.agents.items()), key=lambda d: -d["runs"]),
            "models": {m: {**u, "avg_latency_ms": round(u["latency_ms"] / max(1, u["calls"]), 1)} for m, u in self.model_usage.items()},
            "recent_runs": list(self.recent_runs)[-60:],
        }


OBS = Observability()
