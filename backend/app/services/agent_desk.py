"""Microsoft Agent Framework workflow for the virtual performance-analysis desk."""
from __future__ import annotations

import time

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from app.services.observability import OBS
from app.services.tracing import span


class EvidenceAnalyst(Executor):
    def __init__(self, service, runtime) -> None:
        super().__init__("evidence_analyst")
        self.service, self.runtime = service, runtime

    @handler
    async def collect(self, message: dict, ctx: WorkflowContext[dict]) -> None:
        started = time.perf_counter()
        with span("agent_framework.desk.evidence", match_id=self.runtime.match_id, agent_name=self.id):
            evidence = self.service.evidence(self.runtime)
        await ctx.send_message({**message, "evidence": evidence, "stages": [{"agent": self.id, "status": "complete",
                                  "latency_ms": round((time.perf_counter() - started) * 1000, 1), "model": "deterministic"}]})


class CoachStrategist(Executor):
    def __init__(self, service) -> None:
        super().__init__("coach_strategist")
        self.service = service

    @handler
    async def analyse(self, message: dict, ctx: WorkflowContext[dict]) -> None:
        started = time.perf_counter()
        report = await self.service.analyse(message["evidence"])
        stages = [*message["stages"], {"agent": self.id, "status": "complete",
                  "latency_ms": round((time.perf_counter() - started) * 1000, 1), "model": report.get("model")}]
        await ctx.send_message({**message, "report": report, "stages": stages})


class EvidenceVerifier(Executor):
    def __init__(self, service) -> None:
        super().__init__("evidence_verifier")
        self.service = service

    @handler
    async def verify(self, message: dict, ctx: WorkflowContext[dict]) -> None:
        started = time.perf_counter()
        with span("agent_framework.desk.verify", match_id=message["match_id"], agent_name=self.id):
            report = self.service.verify(message["report"], message["evidence"])
        stages = [*message["stages"], {"agent": self.id, "status": "complete",
                  "latency_ms": round((time.perf_counter() - started) * 1000, 1), "model": "deterministic",
                  "passed": report["verification"]["passed"]}]
        await ctx.send_message({**message, "report": report, "stages": stages})


class ReportPublisher(Executor):
    def __init__(self, service) -> None:
        super().__init__("report_publisher")
        self.service = service

    @handler
    async def publish(self, message: dict, ctx: WorkflowContext[None, dict]) -> None:
        started = time.perf_counter()
        with span("agent_framework.desk.publish", match_id=message["match_id"], agent_name=self.id):
            report = self.service.publish(message["report"], message["evidence"])
        stages = [*message["stages"], {"agent": self.id, "status": "complete",
                  "latency_ms": round((time.perf_counter() - started) * 1000, 1), "model": "reportlab"}]
        await ctx.yield_output({"report": report, "stages": stages})


class AgentDesk:
    """A fresh Agent Framework workflow is built per run so parallel requests are isolated."""
    framework = "Microsoft Agent Framework"

    def __init__(self, report_service) -> None:
        self.report_service = report_service

    async def run(self, runtime) -> dict:
        evidence = EvidenceAnalyst(self.report_service, runtime)
        coach = CoachStrategist(self.report_service)
        verifier = EvidenceVerifier(self.report_service)
        publisher = ReportPublisher(self.report_service)
        workflow = (WorkflowBuilder(start_executor=evidence, name="football-performance-desk",
                                    description="Evidence -> coach strategy -> verification -> PDF")
                    .add_chain([evidence, coach, verifier, publisher]).build())
        started = time.perf_counter()
        with span("agent_framework.workflow", match_id=runtime.match_id, workflow_name="football-performance-desk"):
            result = await workflow.run({"match_id": runtime.match_id})
        output = result.get_outputs()[-1]
        OBS.incr("agent_framework_workflows")
        OBS.incr("coach_reports")
        return {**output, "framework": self.framework, "workflow": "football-performance-desk",
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "a2a_endpoint": "/a2a", "mcp_tools": 8}
