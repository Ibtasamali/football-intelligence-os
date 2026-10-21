"""OpenTelemetry setup plus a small in-process span store for the demo dashboard.

Azure Monitor remains the production exporter.  The ring exporter is deliberately
metadata-only: prompts, answers and credentials are never retained.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult, SpanExporter


def _value(value):
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return [str(v) for v in value[:12]]
    return str(value)[:300]


_QUIET = ("GET ", "WS ", "HEAD ", "OPTIONS ")


def _noise(s) -> bool:
    """Framework internals and dashboard polling would bury the agent traces; they still reach Azure Monitor."""
    return s.name.startswith("fastapi.") or s.name.startswith(_QUIET) or s.name == "POST /api/voice/tts"


def _kind(name: str) -> str:
    if name.startswith("langgraph.") or name.startswith("node "):
        return "langgraph"
    if name.startswith("agent "):
        return "agent"
    if name.startswith(("llm.", "chat ")):
        return "llm"
    if name.startswith(("agent_framework", "workflow", "executor", "edge_group", "invoke_agent", "execute_tool", "message.send")):
        return "agent_framework"
    if name.split(" ")[0] in ("POST", "PUT", "PATCH", "DELETE"):
        return "http"
    return "service"


class RingSpanExporter(SpanExporter):
    def __init__(self, size: int = 1000) -> None:
        self.spans: deque[dict] = deque(maxlen=size)
        self._lock = threading.Lock()

    def export(self, spans) -> SpanExportResult:
        rows = []
        for s in spans:
            if _noise(s):
                continue
            ctx = s.get_span_context()
            parent = s.parent.span_id if s.parent else None
            attrs = {str(k): _value(v) for k, v in dict(s.attributes or {}).items()
                     if not any(secret in str(k).lower() for secret in ("prompt", "content", "message", "api_key"))}
            rows.append({
                "trace_id": f"{ctx.trace_id:032x}", "span_id": f"{ctx.span_id:016x}",
                "parent_span_id": f"{parent:016x}" if parent else None,
                "name": s.name, "kind": _kind(s.name), "start_ms": round(s.start_time / 1_000_000, 3),
                "duration_ms": round((s.end_time - s.start_time) / 1_000_000, 2),
                "status": s.status.status_code.name.lower(),
                "error": str(s.status.description or "")[:240], "attributes": attrs,
            })
        with self._lock:
            self.spans.extend(rows)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def snapshot(self, match_id: str | None = None, limit: int = 300) -> list[dict]:
        with self._lock:
            rows = list(self.spans)
        if match_id:
            rows = [r for r in rows if r["attributes"].get("match.id") in (None, match_id)]
        return rows[-limit:]


SPAN_EXPORTER = RingSpanExporter()
_configured = False


def configure_tracing() -> None:
    """Attach the local exporter without replacing Azure Monitor when it is configured."""
    global _configured
    if _configured:
        return
    provider = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(SPAN_EXPORTER))
    try:
        from agent_framework.observability import enable_instrumentation
        enable_instrumentation(enable_sensitive_data=False, enable_message_events=False)
    except ImportError:
        pass
    _configured = True


@contextmanager
def span(name: str, **attributes):
    tracer = trace.get_tracer("football-intelligence-os", "1.0.0")
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key.replace("_", "."), _value(value))
        try:
            yield current
        except Exception as exc:
            current.record_exception(exc)
            current.set_status(trace.Status(trace.StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
            raise


def trace_summary(match_id: str | None = None, limit: int = 300) -> dict:
    rows = SPAN_EXPORTER.snapshot(match_id, limit)
    durations = sorted(r["duration_ms"] for r in rows)

    def percentile(p: float) -> float:
        if not durations:
            return 0.0
        return durations[min(len(durations) - 1, round((len(durations) - 1) * p))]

    traces = {}
    for row in rows:
        traces.setdefault(row["trace_id"], []).append(row)
    summaries = []
    for tid, group in traces.items():
        ids = {r["span_id"] for r in group}
        roots = [r for r in group if not r["parent_span_id"] or r["parent_span_id"] not in ids]
        root = min(roots or group, key=lambda r: r["start_ms"])
        end = max(r["start_ms"] + r["duration_ms"] for r in group)
        summaries.append({"trace_id": tid, "name": root["name"], "kind": root["kind"], "start_ms": root["start_ms"],
                          "duration_ms": round(end - min(r["start_ms"] for r in group), 1), "spans": len(group),
                          "errors": sum(r["status"] == "error" for r in group),
                          "llm_calls": sum(r["kind"] == "llm" for r in group),
                          "agents": sum(r["kind"] == "agent" for r in group),
                          "tokens": sum(int(r["attributes"].get("gen_ai.usage.input_tokens", 0) or 0)
                                        + int(r["attributes"].get("gen_ai.usage.output_tokens", 0) or 0) for r in group)})
    summaries.sort(key=lambda t: -t["start_ms"])
    return {
        "spans": rows, "traces": summaries, "trace_count": len(traces), "span_count": len(rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "p50_ms": percentile(.50), "p95_ms": percentile(.95),
        "generated_at": time.time(),
        "export": "Azure Application Insights + local dashboard",
        "sensitive_data_captured": False,
    }
