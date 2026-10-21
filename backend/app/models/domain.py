"""Domain models shared by the engine, agents, graph and API."""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class EventType(str, Enum):
    KICK_OFF = "KICK_OFF"
    PASS = "PASS"
    CARRY = "CARRY"
    SHOT = "SHOT"
    GOAL = "GOAL"
    TACKLE = "TACKLE"
    INTERCEPTION = "INTERCEPTION"
    FOUL = "FOUL"
    CORNER = "CORNER"
    OFFSIDE = "OFFSIDE"
    SUBSTITUTION = "SUBSTITUTION"
    CARD = "CARD"
    POSSESSION_CHANGE = "POSSESSION_CHANGE"
    PRESSURE = "PRESSURE"
    RECOVERY = "RECOVERY"
    SAVE = "SAVE"
    HALF_TIME = "HALF_TIME"
    FULL_TIME = "FULL_TIME"


DEFENSIVE_ACTIONS = {EventType.TACKLE, EventType.INTERCEPTION, EventType.FOUL, EventType.RECOVERY, EventType.PRESSURE}


class PlayerPosition(BaseModel):
    player_id: str
    team_id: str
    x: float
    y: float


class MatchEvent(BaseModel):
    """A single event. Coordinates are absolute metres: home attacks towards x=105, away towards x=0."""

    event_id: str = Field(default_factory=lambda: new_id("ev"))
    match_id: str
    seq: int
    minute: int
    second: int = 0
    type: EventType
    team_id: str | None = None
    player_id: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    outcome: str | None = None  # success | fail | on_target | off_target | blocked | yellow | red ...
    related_player_id: str | None = None  # receiver / player off / fouled player
    meta: dict[str, Any] = Field(default_factory=dict)
    positions: list[PlayerPosition] = Field(default_factory=list)

    @property
    def clock(self) -> str:
        return f"{self.minute:02d}:{self.second:02d}"

    @property
    def game_seconds(self) -> int:
        return self.minute * 60 + self.second


class Player(BaseModel):
    player_id: str
    team_id: str
    name: str
    number: int
    position: str  # GK, RB, CB, LB, DM, CM, AM, RW, LW, ST
    role: str = ""
    bench: bool = False


class Team(BaseModel):
    team_id: str
    name: str
    short_name: str
    colors: dict[str, str]
    formation: str
    style: str
    coach: str


class Match(BaseModel):
    match_id: str
    home_team_id: str
    away_team_id: str
    competition: str
    venue: str
    kickoff: str
    status: str = "scheduled"  # scheduled | live | finished
    score: dict[str, int] = Field(default_factory=dict)
    synthetic: bool = True
    tenant_id: str = "demo"
    source: str = "synthetic"            # synthetic | statsbomb | external
    duration_minutes: int = 90
    notes: dict[str, Any] = Field(default_factory=dict)  # e.g. penalty shoot-out result, attribution


class Provenance(BaseModel):
    source_events: list[str] = Field(default_factory=list)
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    memories: list[dict[str, Any]] = Field(default_factory=list)
    model: str = "none"
    agents_used: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    cache_hit: bool = False
    graph_path: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str
    event_ids: list[str] = Field(default_factory=list)
    metric_refs: list[str] = Field(default_factory=list)
    verified: bool = False
    reason: str = ""


class Prediction(BaseModel):
    label: str
    probability: float
    horizon: str
    basis: str
    kind: str = "prediction"


class Insight(BaseModel):
    insight_id: str = Field(default_factory=lambda: new_id("ins"))
    match_id: str
    event_id: str | None = None
    minute: int = 0
    second: int = 0
    category: str  # GOAL | TURNING_POINT | TACTICAL_SHIFT | HIGH_PRESS | DANGEROUS_ATTACK | PLAYER_IMPACT | MOMENTUM_SHIFT | ANSWER
    headline: str
    explanations: dict[str, str] = Field(default_factory=dict)  # beginner/intermediate/advanced/professional
    commentary: str = ""
    perspectives: dict[str, str] = Field(default_factory=dict)  # team_id -> fan framing
    voice_scripts: dict[str, str] = Field(default_factory=dict)  # persona -> spoken line
    historical_note: str = ""
    verification: dict[str, Any] = Field(default_factory=dict)
    significance: float = 0.0
    team_id: str | None = None
    player_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    predictions: list[Prediction] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    statistics: dict[str, Any] = Field(default_factory=dict)
    visualization: list[dict[str, Any]] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    created_at: float = Field(default_factory=time.time)


class AgentResult(BaseModel):
    agent: str
    agent_run_id: str = Field(default_factory=lambda: new_id("run"))
    status: str = "complete"  # complete | skipped | failed | cached
    output: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    evidence_event_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    tokens: int = 0
    model: str = "none"
    error: str | None = None


class KnowledgeLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    PROFESSIONAL = "professional"


class Persona(str, Enum):
    CASUAL_COMMENTATOR = "casual_commentator"
    TACTICAL_ANALYST = "tactical_analyst"
    COACH = "coach"
    KIDS = "kids"
    EXPERT_ANALYST = "expert_analyst"


class FanProfile(BaseModel):
    user_id: str
    tenant_id: str = "demo"
    display_name: str = "Fan"
    favorite_team_id: str | None = None
    favorite_player_id: str | None = None
    knowledge_level: KnowledgeLevel = KnowledgeLevel.INTERMEDIATE
    language: str = "en"
    persona: Persona = Persona.CASUAL_COMMENTATOR
    interests: list[str] = Field(default_factory=list)
