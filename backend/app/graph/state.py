"""FootballState — the LangGraph state shared by the event graph and the query graph."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class FootballState(TypedDict, total=False):
    # identity
    run_id: str
    mode: str                       # "event" | "query"
    trace: bool                     # walkthrough run: bypass cache, never publish
    match_id: str
    timestamp: float
    tenant_id: str
    # event
    event: dict
    event_obj: Any
    event_delta: dict
    event_summary: str
    pattern_changes: list
    new_patterns: list[dict]
    ended_patterns: list[dict]
    frozen: dict
    # query
    question: str
    focus_insight_id: str | None
    intent: str
    user_id: str
    profile: dict
    level: str
    persona: str
    # entities / context
    player: str | None
    team: str | None
    team_id: str | None
    opponent: str | None
    team_ids: list[str]
    player_ids: list[str]
    score: dict
    formation: dict
    tactical_context: dict
    cached_context: dict
    cached_context_sufficient: bool
    # routing
    significance: float
    tactical_significance: float
    category: str
    reasons: list[str]
    routing: dict
    model_tier: str
    retrieval_reason: str
    # knowledge
    retrieved_documents: list[dict]
    memories: list[dict]
    # results
    agent_results: Annotated[dict, merge_dicts]
    confidence_scores: Annotated[dict, merge_dicts]
    momentum: dict
    predictions: list[dict]
    narrative: dict
    first_draft: dict
    verification: dict
    verification_attempts: int
    verification_feedback: list[str]
    voice_script: str
    visualization_command: list[dict]
    final_insight: dict
    cache_key: str
    cache_hit: bool
    graph_path: Annotated[list[str], operator.add]
