"""Reasoning agents.

Cost design: the Expert Analyst runs ONE structured LLM call that produces every explanation level,
the broadcast line, the historical note and machine-checkable claims. The Casual Fan, Broadcast
Commentary and Storytelling agents are facet agents that validate and shape their part of that output
deterministically, so four "writer" agents cost one call — and that one result is shared by every fan
watching the match.
"""
from __future__ import annotations

import json

from app.agents.base import Agent, AgentContext
from app.agents.evidence import build_evidence, verify_output
from app.data.teams import team_name
from app.prediction.models import predict

SYSTEM_PROMPT = """You are the reasoning core of Football Intelligence OS, a live football analysis system.
You receive EVIDENCE computed by deterministic tactical agents. Write grounded explanations.

HARD RULES
1. Use ONLY facts present in EVIDENCE. Never invent players, events, minutes, matches or statistics.
2. Every number you write must appear in EVIDENCE (you may round, or write a 0–1 share as a percentage).
3. Predictions are probabilities: say "likely", "around X%". Never state the future as fact.
4. Historical matches may only be mentioned if listed in EVIDENCE.documents; use their exact title.
5. Explain WHY (cause → effect), not just what. Name the tactical mechanism.
6. If evidence is thin, say so briefly instead of speculating.
7. EVIDENCE.match.score_text is the score right after this event and goals_so_far lists every goal scored; never
   contradict them (who scored, who leads, who equalised).
8. Write team and player names exactly as in EVIDENCE.
9. Never expose internals in prose: no event ids, sequence numbers, raw x/y coordinates or model scores like
   "influence 73.4". Translate locations into football language (left flank, edge of the box, own half).

OUTPUT strictly as JSON:
{
 "headline": "≤ 9 words, punchy, factual",
 "explanations": {
   "beginner": "1–2 short sentences, zero jargon, friendly",
   "intermediate": "2 sentences, light terminology",
   "advanced": "3 sentences, mechanism + 1–2 numbers",
   "professional": "3–4 sentences, precise metrics (PPDA, xG, field tilt, line height), cite comparison if any"
 },
 "commentary": "one broadcast-style line, ≤ 22 words, vivid but factual",
 "historical_note": "one sentence linking to a retrieved historical match or memory, or empty string",
 "claims": [{"text": "atomic factual claim", "event_ids": ["ev_..."], "metric_refs": ["key from EVIDENCE.metrics"]}],
 "confidence": 0.0-1.0
}
Provide 2–4 claims. Use event ids from EVIDENCE.valid_event_ids only."""

ANSWER_PROMPT = SYSTEM_PROMPT.replace(
    "You receive EVIDENCE computed by deterministic tactical agents. Write grounded explanations.",
    "A fan asked EVIDENCE.question. Answer it directly using EVIDENCE computed by tactical agents. "
    "The headline is the short answer; explanations give the answer at each knowledge level.")


def normalize_narrative(data: dict) -> dict:
    """Coerce LLM JSON into the exact shape downstream agents and the verifier expect."""
    def as_list(v):
        if v is None:
            return []
        if isinstance(v, (str, int, float)):
            return [str(v)]
        return [str(x) for x in v if x is not None]

    claims = []
    for c in data.get("claims") or []:
        if isinstance(c, str):
            claims.append({"text": c, "event_ids": [], "metric_refs": []})
        elif isinstance(c, dict) and c.get("text"):
            claims.append({"text": str(c["text"]), "event_ids": as_list(c.get("event_ids")),
                           "metric_refs": as_list(c.get("metric_refs"))})
    ex = data.get("explanations") if isinstance(data.get("explanations"), dict) else {}
    try:
        conf = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        conf = 0.7
    return {**data, "headline": str(data.get("headline") or ""), "commentary": str(data.get("commentary") or ""),
            "historical_note": str(data.get("historical_note") or ""),
            "explanations": {k: str(ex.get(k) or "") for k in ("beginner", "intermediate", "advanced", "professional")},
            "claims": claims[:6], "confidence": max(0.0, min(1.0, conf))}


def _pct(v) -> str:
    return f"{round(v * 100)}%" if isinstance(v, (int, float)) else "n/a"


def local_narrative(evidence: dict, state: dict) -> dict:
    """Template narrative from evidence only — used without Azure OpenAI or on LLM failure."""
    a = evidence.get("analysis", {})
    interp = a.get("event_interpretation", {})
    if state.get("mode") == "query":
        return local_answer(evidence, state)
    new_types = {p["type"] for p in state.get("new_patterns") or []}
    pats = [p for p in evidence.get("patterns", []) if p["type"] in new_types]
    cat = state.get("category", "")
    team = interp.get("team") or ""
    claims, ev_ids = [], [i for i in [interp.get("event_id")] if i]
    if pats:
        p = pats[0]
        headline = {"HIGH_PRESS": f"{team_name(p['team_id'])} switch on the high press",
                    "FLANK_OVERLOAD": f"{team_name(p['team_id'])} overload the flank",
                    "DEEP_BLOCK": f"{team_name(p['team_id'])} drop into a deep block",
                    "TRANSITION_VULNERABILITY": f"{team_name(p['team_id'])} exposed on the counter",
                    "MIDFIELD_SUPERIORITY": f"{team_name(p['team_id'])} control midfield"}.get(p["type"], p["type"].title())
        pro = p["summary"]
        claims.append({"text": p["summary"], "event_ids": p.get("evidence_event_ids", [])[:3], "metric_refs": []})
        beginner = {"HIGH_PRESS": f"{team_name(p['team_id'])} are chasing the ball near the other goal to win it back quickly.",
                    "FLANK_OVERLOAD": f"{team_name(p['team_id'])} keep sending extra players down one side to get past the defence.",
                    "DEEP_BLOCK": f"{team_name(p['team_id'])} are defending close to their own goal to protect the score.",
                    "TRANSITION_VULNERABILITY": f"{team_name(p['team_id'])} leave space behind when they lose the ball, so the other team can break fast.",
                    "MIDFIELD_SUPERIORITY": f"{team_name(p['team_id'])} have more players in the middle, so they keep the ball easily."}.get(p["type"], p["summary"])
    elif state.get("ended_patterns"):
        p = state["ended_patterns"][0]
        ended_text = {"HIGH_PRESS": "ease off the high press", "FLANK_OVERLOAD": "stop overloading the flank",
                      "DEEP_BLOCK": "step out of their deep block", "TRANSITION_VULNERABILITY": "close the gaps in transition",
                      "MIDFIELD_SUPERIORITY": "lose their midfield control"}.get(p["type"], "change shape")
        headline = f"{team_name(p['team_id'])} {ended_text}"
        beginner = f"{team_name(p['team_id'])} have changed what they were doing — the earlier pattern has stopped."
        pro = f"Pattern ended: {p['summary']} The detector no longer sees it in the last 5 minutes."
        claims.append({"text": pro, "event_ids": ev_ids, "metric_refs": []})
    else:
        headline = interp.get("label", "Key moment")
        pro = interp.get("description", "")
        beginner = interp.get("description", "")
        ev_type = (evidence.get("event") or {}).get("type")
        subs = a.get("substitution_impact", {}).get("substitutions", [])
        if ev_type == "SUBSTITUTION" and subs:
            s0 = subs[-1]
            headline = f"{team}: {s0['on_name']} on for {s0['off_name']}"
            beginner = f"{team} bring on {s0['on_name']} to change how they play."
            pro = f"{headline}. Stated intent: {s0.get('reason') or 'not given'}. Impact will be measured over equal windows before and after the change."
        elif cat == "MOMENTUM_SHIFT":
            mom = a.get("momentum", {})
            headline = f"Momentum swings towards {mom.get('leader_name', team)}"
            beginner = f"{mom.get('leader_name', team)} are on top right now and pushing forward."
            pro = f"{interp.get('description', '')}. Momentum index {mom.get('index')} (3-min trend {mom.get('trend_3min')})."
        elif cat == "HIGH_PRESS" and interp.get("label") == "High turnover":
            headline = f"{interp.get('player', '')} wins it back high up the pitch"
            beginner = f"{interp.get('player', '')} steals the ball close to the other team's goal."
        elif ev_type == "CARD":
            headline = f"Booking for {interp.get('player', '')}"
            beginner = f"{interp.get('player', '')} gets a card for a foul."
    gp = a.get("goal_probability", {})
    if cat == "DANGEROUS_ATTACK" and gp.get("shot_xg") is not None:
        ev_outcome = (evidence.get("event") or {}).get("outcome") or ""
        verb = {"saved": "denied by the keeper", "off_target": "off target", "blocked": "blocked"}.get(ev_outcome, ev_outcome)
        headline = f"{gp.get('shot_quality', 'Chance').capitalize()} for {interp.get('player', '')} — {verb}"
        beginner = f"{interp.get('player', '')} had a {'great' if gp['shot_xg'] >= 0.3 else 'decent' if gp['shot_xg'] >= 0.1 else 'hopeful'} chance to score for {team}, but it was {verb}."
    if cat == "GOAL":
        headline = f"GOAL — {interp.get('player', '')} scores for {team}"
        beginner = f"{interp.get('player', '')} scores for {team}! " + evidence["match"]["score_text"] + "."
        if gp.get("conversion_note"):
            pro = f"{interp.get('description', '')}. {gp['conversion_note']}"
    if gp.get("shot_xg") is not None and cat != "GOAL":
        pro += f" Shot quality: {gp.get('shot_quality')} (xG {gp['shot_xg']})."
    preds = evidence.get("predictions", [])
    pred_line = f" Model estimate: {preds[0]['label'].lower()} — {_pct(preds[0]['probability'])}." if preds else ""
    docs = evidence.get("documents", [])
    hist = f"This echoes {docs[0]['title']} in the archive." if docs else ""
    mom = a.get("momentum", {})
    inter = f"{interp.get('description', headline)}. Momentum currently favours {mom.get('leader_name', 'neither side')}."
    return {"headline": headline[:80], "explanations": {
        "beginner": beginner, "intermediate": inter,
        "advanced": f"{pro}{pred_line}", "professional": f"{pro} {hist}{pred_line}".strip()},
        "commentary": f"{evidence['match']['clock']} — {headline}!",
        "historical_note": hist,
        "claims": claims or [{"text": interp.get("description", headline), "event_ids": ev_ids, "metric_refs": []}],
        "confidence": 0.7 if pats or cat == "GOAL" else 0.55}


def local_answer(evidence: dict, state: dict) -> dict:
    """Intent-aware grounded answer without an LLM."""
    intent = state.get("intent", "GENERAL")
    focus = evidence.get("focus_moment") or {}
    top = evidence.get("top_players", [])
    totals = evidence.get("match_totals", {})
    preds = evidence.get("predictions", [])
    docs = evidence.get("documents", [])
    a = evidence.get("analysis", {})
    score = evidence["match"]["score_text"]
    if intent == "BEST_PLAYER" and top:
        p = top[0]
        head = f"{p['name']} is the standout player"
        beg = f"{p['name']} has been the most involved and dangerous player so far."
        pro = (f"{p['name']} ({p['position']}) leads the influence model at {p['influence']}: {p['goals']} goals, "
               f"{p['assists']} assists, xG {p['xg']}, xA {p['xa']}, {p['progressive_actions']} progressive actions and "
               f"{p['recoveries']} recoveries.")
        if len(top) > 1:
            pro += f" Next: {top[1]['name']} ({top[1]['influence']})."
    elif intent in ("STATS", "MOMENTUM") and totals:
        parts = [f"{t}: possession {_pct(d['possession'])}, xG {d['xg']}, shots {d['shots']}, PPDA {d['ppda']}" for t, d in totals.items()]
        head = score
        beg = f"The score is {score}. " + " ".join(f"{t} have had {_pct(d['possession'])} of the ball." for t, d in totals.items())
        pro = "; ".join(parts) + "."
    elif intent == "PREDICT" and preds:
        top_p = sorted(preds, key=lambda p: -p["probability"])[:3]
        head = f"Most likely: {top_p[0]['label'].lower()}"
        beg = f"The model thinks {top_p[0]['label'].lower()} is about {_pct(top_p[0]['probability'])} likely — a guess, not a certainty."
        pro = " ".join(f"{p['label']}: {_pct(p['probability'])} ({p['basis']})." for p in top_p)
    elif intent in ("COMPARE", "SIMILAR") and docs:
        d = docs[0]
        head = f"Closest match: {d['title']}"
        beg = f"Something similar happened in {d['title']}."
        pro = f"{d['title']}: {d['snippet'][:380]}"
        if focus:
            pro = f"Now ({focus['clock']}): {focus['headline']}. Then — {pro}"
    elif focus:
        head = focus["headline"]
        beg = focus["headline"] + "."
        pro = focus.get("explanation") or focus["headline"]
    else:
        head = score
        beg = f"The score is {score}."
        pro = a.get("tactical_analysis", {}).get("summary", beg)
    return {"headline": head[:90], "explanations": {"beginner": beg, "intermediate": beg if len(pro) > 260 else pro,
                                                    "advanced": pro, "professional": pro},
            "commentary": head, "historical_note": f"Related: {docs[0]['title']}." if docs else "",
            "claims": [{"text": pro[:300], "event_ids": focus.get("event_ids", [])[:3], "metric_refs": []}],
            "confidence": 0.7 if (focus or top or docs) else 0.5}


class PredictionAgent(Agent):
    name, family = "prediction", "reasoning"
    description = "Probabilistic next-state predictions (goal threat, next action, counter danger)."

    async def execute(self, ctx: AgentContext):
        eng = ctx.runtime.engine
        cur = ctx.event.type.value if ctx.event else (eng.events[-1].type.value if eng.events else "PASS")
        preds = predict(eng, cur, ctx.runtime.patterns.active_list())
        return {"predictions": [p.model_dump() for p in preds]}, 0.6, []


class ExpertAnalystAgent(Agent):
    name, family, uses_llm = "expert_analyst", "reasoning", True
    description = "Lead reasoning agent: one structured LLM call producing all explanation facets + claims."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        evidence = build_evidence(st, ctx.runtime)
        feedback = st.get("verification_feedback")
        payload = {k: v for k, v in evidence.items() if k not in ("metrics", "valid_event_ids")}
        payload["valid_event_ids"] = evidence["valid_event_ids"][-25:]
        payload["metric_keys"] = list(evidence["metrics"].keys())[:40]
        user = "EVIDENCE:\n" + json.dumps(payload, default=str, separators=(",", ":"))[:7500]
        if st.get("new_patterns"):
            p0 = st["new_patterns"][0]
            user += (f"\n\nFOCUS: a NEW tactical pattern was just detected — {p0['type']} by {team_name(p0['team_id'])}. "
                     f"The headline and explanations must be about this pattern (what it is, why it is happening, what it "
                     f"changes), not about the single event that triggered detection.")
        elif st.get("ended_patterns"):
            user += f"\n\nFOCUS: the pattern {st['ended_patterns'][0]['type']} has just ENDED. Explain what changed."
        intent_focus = {
            "COMPARE": "Compare NOW with the best historical match in EVIDENCE.documents: name it by exact title in the "
                       "headline, then give 1–2 similarities and 1 difference.",
            "SIMILAR": "Name the most similar historical match from EVIDENCE.documents by exact title and explain why it is similar.",
            "BEST_PLAYER": "Name the best player using EVIDENCE.top_players and justify with 2 of their numbers.",
            "PREDICT": "Answer with probabilities from EVIDENCE.predictions, explicitly labelled as estimates.",
            "WHY": "Explain the cause → effect chain behind EVIDENCE.focus_moment.",
        }.get(st.get("intent", ""))
        if st.get("question") and intent_focus:
            user += f"\n\nANSWER FOCUS: {intent_focus}"
        if feedback:
            user += "\n\nYOUR PREVIOUS DRAFT FAILED VERIFICATION. Fix these issues:\n- " + "\n- ".join(feedback[:8])
        prompt = ANSWER_PROMPT if st.get("question") else SYSTEM_PROMPT
        res = await ctx.services.llm.complete_json(system=prompt, user=user, tier=st.get("model_tier", "small"),
                                                   fallback=lambda: local_narrative(evidence, st), max_tokens=1000,
                                                   interactive=bool(st.get("question")))
        data = normalize_narrative(res.data)
        data["_evidence"] = evidence
        data["_model"] = res.model + (" (cached)" if res.cached else "")
        data["_tokens"] = res.tokens
        data["llm_latency_ms"] = round(res.latency_ms, 1)
        data["fallback"] = res.fallback
        return data, float(data.get("confidence", 0.7) or 0.7), evidence["valid_event_ids"][:10]


class CasualFanExplanationAgent(Agent):
    name, family = "casual_fan_explanation", "reasoning"
    description = "Facet: guarantees a jargon-free beginner explanation."

    JARGON = {"ppda": "how hard they press", "xg": "chance quality", "field tilt": "territory",
              "transition": "counter-attack", "low block": "deep defending", "half-space": "inside channel"}

    async def execute(self, ctx: AgentContext):
        draft = ctx.result("expert_analyst").get("explanations", {})
        text = draft.get("beginner") or draft.get("intermediate") or ""
        replaced = []
        for j, plain in self.JARGON.items():
            if j in text.lower():
                import re
                text = re.sub(j, plain, text, flags=re.I)
                replaced.append(j)
        return {"beginner": text.strip(), "jargon_replaced": replaced}, 0.85, []


class BroadcastCommentaryAgent(Agent):
    name, family = "broadcast_commentary", "experience"
    description = "Facet: a broadcast line capped for live captions."

    async def execute(self, ctx: AgentContext):
        line = (ctx.result("expert_analyst").get("commentary") or "").strip()
        words = line.split()
        if len(words) > 26:
            line = " ".join(words[:26]).rstrip(",;") + "…"
        return {"commentary": line}, 0.85, []


class StorytellingAgent(Agent):
    name, family = "storytelling", "reasoning"
    description = "Facet: decides whether this moment is a story beat (turning point, momentum swing, tactical shift)."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        mom = ctx.result("momentum")
        beats = []
        if st.get("category") == "GOAL":
            beats.append("score_change")
        if mom.get("shift"):
            beats.append("momentum_swing")
        if st.get("new_patterns"):
            beats.append("tactical_shift")
        if st.get("event_obj") and st["event_obj"].type.value == "SUBSTITUTION":
            beats.append("tactical_change")
        if st.get("category") == "DANGEROUS_ATTACK" and (ctx.result("goal_probability").get("shot_xg") or 0) >= 0.3:
            beats.append("big_chance")
        weight = min(1.0, st.get("significance", 0) + 0.1 * len(beats))
        return {"story_beats": beats, "turning_point": weight >= 0.8 and bool(beats), "story_weight": round(weight, 2)}, 0.75, []


class FactVerificationAgent(Agent):
    name, family = "fact_verification", "reasoning"
    description = "Checks event IDs, metrics, numbers, sources and prediction wording against evidence."

    async def execute(self, ctx: AgentContext):
        draft = ctx.result("expert_analyst")
        evidence = draft.get("_evidence") or build_evidence(ctx.state, ctx.runtime)
        report = verify_output(draft, evidence, ctx.runtime.engine)
        return report, report["claim_support"], [i for c in report["verified_claims"] for i in c.get("event_ids", [])][:10]


class AlertAgent(Agent):
    name, family = "alert", "reasoning"
    description = "Decides whether to push a notification and at which priority."

    async def execute(self, ctx: AgentContext):
        st = ctx.state
        cat = st.get("category")
        preds = st.get("predictions", [])
        danger = [p for p in preds if "counter" in p["label"] and p["probability"] >= 0.5]
        if cat == "GOAL":
            level, text = "critical", "Goal"
        elif danger:
            level, text = "danger", danger[0]["label"]
        elif st.get("new_patterns"):
            level, text = "tactical", st["new_patterns"][0]["type"].replace("_", " ").title()
        elif st.get("significance", 0) >= 0.6:
            level, text = "notable", st.get("category", "").replace("_", " ").title()
        else:
            level, text = "none", ""
        return {"level": level, "text": text}, 0.9, []
