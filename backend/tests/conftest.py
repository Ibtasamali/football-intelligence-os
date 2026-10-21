"""Shared fixtures: an isolated container (mock MongoDB, in-memory KV, LLM disabled → local reasoner)."""
from __future__ import annotations

import os

import pytest

os.environ["ENVIRONMENT"] = "test"

from app.core.config import Settings  # noqa: E402
from app.data.synthetic import generate_demo_match  # noqa: E402
from app.models.domain import Match  # noqa: E402
from app.services.container import Container  # noqa: E402
from app.tactical.engine import TacticalEngine  # noqa: E402
from app.tactical.patterns import PatternTracker  # noqa: E402


@pytest.fixture(scope="session")
def events():
    return generate_demo_match("test-match")


@pytest.fixture(scope="session")
def played(events):
    """Engine + pattern tracker after the full match, with the minute each pattern started."""
    eng = TacticalEngine("test-match", "azc", "tha")
    tracker = PatternTracker()
    starts = []
    for e in events:
        eng.update(e)
        for kind, p in tracker.update(eng):
            if kind == "start":
                starts.append((e.minute, p.type, p.team_id, p))
    return eng, tracker, starts


@pytest.fixture
async def container():
    s = Settings(_env_file=None, environment="test", azure_openai_api_key="", azure_speech_key="", redis_url="")
    c = Container(s)
    await c.start(use_mock_db=True, use_memory_kv=True, enable_llm=False)
    yield c
    await c.stop()


@pytest.fixture
async def loaded(container, events):
    """Container with the match ingested up to 62' (both early goals + several patterns), deep path drained."""
    m = Match(match_id="test-match", home_team_id="azc", away_team_id="tha", competition="t", venue="v", kickoff="k")
    rt = await container.create_match(m)
    for e in events:
        if e.minute >= 62:
            break
        await container.ingest(e, persist=False)
    await container.pool.drain(120)
    return container, rt
