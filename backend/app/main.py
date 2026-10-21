"""Football Intelligence OS — FastAPI gateway."""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (routes_a2a, routes_agents, routes_events, routes_fans, routes_insights, routes_matches, routes_players,
                     routes_teams, routes_voice, ws)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.security import RateLimiter
from app.services.container import Container
from app.services.tracing import configure_tracing

settings = get_settings()
configure_logging(settings.log_level)

if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    # OpenTelemetry → Application Insights: requests, dependencies (Azure OpenAI, Mongo, Redis) and logs.
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor(logger_name="app")
    except ImportError:
        pass
configure_tracing()
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = Container(settings)
    test = settings.environment == "test"
    await container.start(use_mock_db=test, use_memory_kv=test, enable_llm=not test)
    app.state.container = container
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)
    yield
    for r in container.replays.values():
        r.stop()
    await container.stop()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
              description="Every Match. Every Moment. Explained by AI.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def gateway(request: Request, call_next):
    limiter: RateLimiter | None = getattr(request.app.state, "limiter", None)
    client = request.headers.get("x-forwarded-for", request.client.host if request.client else "anon")
    if limiter and request.url.path.startswith("/api") and not limiter.allow(f"ip:{client}"):
        return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        log.exception("unhandled_error", path=request.url.path)
        return JSONResponse({"detail": "internal error", "type": type(exc).__name__}, status_code=500)
    response.headers["x-response-time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    return response


app.include_router(routes_matches.catalog_router)
app.include_router(routes_matches.recap_router)
app.include_router(routes_a2a.router)
for r in (routes_matches, routes_events, routes_agents, routes_voice, routes_insights, routes_players, routes_teams, routes_fans):
    app.include_router(r.router)
app.include_router(ws.router)


@app.get("/health")
async def health():
    c = app.state.container
    return {"status": "ok", "llm": c.llm.enabled, "speech": c.speech.enabled, "kv": c.kv.backend,
            "doc_intelligence": settings.doc_intel_enabled, "matches": list(c.runtimes)}
