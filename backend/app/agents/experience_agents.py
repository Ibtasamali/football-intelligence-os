"""Experience agents: personalisation, voice, 3D visualisation, final assembly."""
from __future__ import annotations

from app.agents.base import Agent, AgentContext
from app.data.teams import team_name
from app.visualization.commands import commands_for_insight
from app.voice.personas import PERSONAS

FAVOURABLE = {"GOAL", "HIGH_PRESS", "FLANK_OVERLOAD", "MIDFIELD_SUPERIORITY", "DANGEROUS_ATTACK", "PLAYER_IMPACT"}


class FanPersonalizationAgent(Agent):
    name, family = "fan_personalization", "experience"
    description = "Builds per-team fan framing; per-user level selection happens at delivery (no extra LLM call)."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        team = st.get("team_id")
        cat = st.get("category", "")
        pattern = (st.get("new_patterns") or [{}])[0]
        perspectives = {}
        for tid in (ctx.runtime.engine.home, ctx.runtime.engine.away):
            if not team:
                continue
            if pattern.get("type") == "TRANSITION_VULNERABILITY":
                good = pattern["team_id"] != tid          # the exposed team is the pattern's team
            elif pattern.get("type") == "DEEP_BLOCK":
                good = None                               # a tactical choice, not good or bad per se
            elif pattern.get("type"):
                good = pattern["team_id"] == tid          # judge by the team DOING the pattern, not the trigger event
            else:
                good = (team == tid) if cat in FAVOURABLE else None
            if good is True:
                perspectives[tid] = f"Good sign for {team_name(tid)} fans."
            elif good is False:
                perspectives[tid] = f"One for {team_name(tid)} fans to worry about."
            else:
                perspectives[tid] = f"A tactical choice {team_name(tid)} fans will want to watch."
        return {"perspectives": perspectives}, 0.8, []


class VoiceNarratorAgent(Agent):
    name, family = "voice_narrator", "experience"
    description = "Writes a spoken line per persona (audio synthesised on demand, cached across fans)."

    async def execute(self, ctx: AgentContext):
        draft = ctx.result("expert_analyst")
        ex = draft.get("explanations", {})
        beginner = ctx.result("casual_fan_explanation").get("beginner") or ex.get("beginner", "")
        commentary = ctx.result("broadcast_commentary").get("commentary") or draft.get("commentary", "")
        level_text = {"beginner": beginner, "intermediate": ex.get("intermediate", ""),
                      "advanced": ex.get("advanced", ""), "professional": ex.get("professional", "")}
        scripts = {}
        for key, p in PERSONAS.items():
            if key == "casual_commentator":
                scripts[key] = commentary or level_text["intermediate"]
            else:
                scripts[key] = level_text.get(p["level"]) or commentary
        return {"voice_scripts": scripts}, 0.85, []


class Visualization3DAgent(Agent):
    name, family = "visualization_3d", "experience"
    description = "Emits declarative 3D scene commands: zones, players, lanes, trajectories, camera, replay."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        rt = ctx.runtime
        eng = rt.engine
        patterns = list(st.get("new_patterns") or [])
        if not patterns and st.get("category") not in ("GOAL", "DANGEROUS_ATTACK"):
            patterns = rt.patterns.active_list()[:1]
        evidence_ids = []
        for p in patterns:
            evidence_ids += p.get("evidence_event_ids", [])
        ev = st.get("event_obj")
        events = [eng.by_id[i] for i in dict.fromkeys(evidence_ids) if i in eng.by_id]
        if ev:
            seq = [e for e in eng.window(25, until=ev.game_seconds)]
            events = sorted({e.event_id: e for e in events + seq}.values(), key=lambda e: e.seq)
        net = ctx.result("passing_network").get("edges")
        cmds = commands_for_insight(category=st.get("category", ""), team_id=st.get("team_id"), home_id=eng.home,
                                    patterns=patterns, events=events, player_ids=st.get("player_ids", []),
                                    network=net, positions_lookup=rt.position_of)
        return {"commands": cmds}, 0.9, [e.event_id for e in events[-6:]]


class FinalAnswerAgent(Agent):
    name, family = "final_answer", "experience"
    description = "Assembles the verified insight with full provenance."

    async def execute(self, ctx: AgentContext):
        # Assembly itself happens in the publish node; this agent scores overall confidence.
        results = ctx.state.get("agent_results", {})
        confs = [r["confidence"] for n, r in results.items() if r.get("status") == "complete" and n != "final_answer"]
        verification = results.get("fact_verification", {}).get("output", {})
        base = sum(confs) / len(confs) if confs else 0.5
        support = verification.get("claim_support", 0.6)
        overall = round(0.55 * base + 0.45 * support, 3)
        return {"overall_confidence": overall, "agents_counted": len(confs)}, overall, []
