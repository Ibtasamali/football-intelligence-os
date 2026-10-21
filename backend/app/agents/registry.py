"""Agent registry: 30 stateless agent templates, instantiated once and shared by all workers."""
from __future__ import annotations

from app.agents.analysis_agents import (
    AttackingAnalysisAgent, DefensiveAnalysisAgent, EventInterpretationAgent, FormationAgent, GoalProbabilityAgent,
    MatchIntelligenceAgent, MomentumAgent, PassingNetworkAgent, PlayerIntelligenceAgent, PressingAnalysisAgent,
    SpaceAnalysisAgent, SubstitutionImpactAgent, TacticalAnalysisAgent, TeamIntelligenceAgent)
from app.agents.base import Agent
from app.agents.experience_agents import (
    FanPersonalizationAgent, FinalAnswerAgent, Visualization3DAgent, VoiceNarratorAgent)
from app.agents.knowledge_agents import (
    CAGContextAgent, HistoricalComparisonAgent, MAGMemoryAgent, RAGRetrievalAgent, SimilarMatchAgent)
from app.agents.reasoning_agents import (
    AlertAgent, BroadcastCommentaryAgent, CasualFanExplanationAgent, ExpertAnalystAgent, FactVerificationAgent,
    PredictionAgent, StorytellingAgent)

AGENT_CLASSES: list[type[Agent]] = [
    MatchIntelligenceAgent, EventInterpretationAgent, TacticalAnalysisAgent, PlayerIntelligenceAgent,
    TeamIntelligenceAgent, FormationAgent, MomentumAgent, GoalProbabilityAgent, DefensiveAnalysisAgent,
    AttackingAnalysisAgent, PassingNetworkAgent, SpaceAnalysisAgent, PressingAnalysisAgent, SubstitutionImpactAgent,
    HistoricalComparisonAgent, SimilarMatchAgent, FanPersonalizationAgent, CasualFanExplanationAgent,
    ExpertAnalystAgent, StorytellingAgent, FactVerificationAgent, RAGRetrievalAgent, CAGContextAgent, MAGMemoryAgent,
    VoiceNarratorAgent, Visualization3DAgent, PredictionAgent, AlertAgent, BroadcastCommentaryAgent, FinalAnswerAgent,
]

AGENTS: dict[str, Agent] = {cls.name: cls() for cls in AGENT_CLASSES}
assert len(AGENTS) == 30, f"expected 30 agents, got {len(AGENTS)}"


def catalog() -> list[dict]:
    return [{"name": a.name, "family": a.family, "uses_llm": a.uses_llm, "description": a.description}
            for a in AGENTS.values()]
