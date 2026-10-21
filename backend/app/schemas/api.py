"""API request/response contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.domain import KnowledgeLevel, Persona


class CreateMatchRequest(BaseModel):
    match_id: str = Field(default="demo-azc-tha", pattern=r"^[a-zA-Z0-9_\-]{3,64}$")
    source: str = Field(default="synthetic", pattern="^(synthetic|statsbomb|external)$")
    statsbomb_key: str | None = Field(default=None, max_length=64)  # one of the curated keys (GET /api/catalog/matches)
    seed: int = 11
    autostart: bool = False
    speed: float = Field(default=20.0, gt=0, le=600)
    director: bool = True


class ReplaySpeedRequest(BaseModel):
    speed: float = Field(gt=0, le=600)
    director: bool | None = None


class JumpRequest(BaseModel):
    minute: float | None = Field(default=None, ge=0, le=125)
    seq: int | None = Field(default=None, ge=0)


class AnalyzeRequest(BaseModel):
    match_id: str
    event_id: str | None = None


class VoiceQueryRequest(BaseModel):
    match_id: str
    text: str = Field(min_length=1, max_length=500)
    user_id: str | None = Field(default=None, max_length=64)
    persona: Persona | None = None
    level: KnowledgeLevel | None = None
    language: str = Field(default="en", max_length=8)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    persona: Persona | None = None
    language: str = Field(default="en", max_length=8)


class TranslateRequest(BaseModel):
    language: str = Field(max_length=8)
    level: KnowledgeLevel = KnowledgeLevel.INTERMEDIATE
    persona: Persona = Persona.CASUAL_COMMENTATOR


class FanProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    favorite_team_id: str | None = None
    favorite_player_id: str | None = None
    knowledge_level: KnowledgeLevel | None = None
    language: str | None = Field(default=None, max_length=8)
    persona: Persona | None = None
    interests: list[str] | None = None


class KnowledgeTextRequest(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=20, max_length=50_000)
    teams: list[str] = []
    patterns: list[str] = []
