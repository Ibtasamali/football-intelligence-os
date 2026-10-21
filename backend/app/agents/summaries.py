"""Plain-language summaries of what each agent found — used by the Pipeline walkthrough (and the demo video)."""
from __future__ import annotations

from app.data.teams import player_name, team_name


def _pct(v):
    return f"{round(v * 100)}%" if isinstance(v, (int, float)) else "–"


def summarize(agent: str, o: dict) -> list[str]:
    o = o or {}
    try:
        if agent == "match_intelligence":
            return [o.get("score_text", ""), f"Game state: {o.get('game_state')} · {o.get('phase')}"]
        if agent == "event_interpretation":
            return [o.get("description", "")]
        if agent == "cag_context":
            return [f"Live context cache {o.get('cache')} (version {o.get('version')}) — no database round-trip",
                    f"Active patterns in cache: {', '.join(o.get('active_patterns') or []) or 'none'}"]
        if agent == "momentum":
            return [f"Momentum index {o.get('index')} → favours {o.get('leader_name')}", f"3-minute trend {o.get('trend_3min')}"
                    + (" · momentum SHIFT" if o.get("shift") else "")]
        if agent == "formation":
            sh = o.get("shapes") or {}
            return [f"{team_name(t)}: live {v.get('live')} (nominal {v.get('nominal')}, {v.get('phase')})" for t, v in sh.items()]
        if agent == "goal_probability":
            out = [f"xG totals: " + ", ".join(f"{team_name(t)} {x}" for t, x in (o.get("xg_totals") or {}).items())]
            if o.get("shot_xg") is not None:
                out.insert(0, f"Shot quality: {o.get('shot_quality')} (xG {o.get('shot_xg')}). {(o.get('conversion_note') or '').replace(' 1 times', ' once')}")
            return out
        if agent == "tactical_analysis":
            return [o.get("summary", "")]
        if agent == "defensive_analysis":
            return [f"{o.get('team')}: defensive line {o.get('line_height_5min')} m (match {o.get('line_height_match')} m)",
                    f"PPDA {o.get('ppda_5min')} (5 min) · compactness {o.get('compactness_m2')} m²"]
        if agent == "attacking_analysis":
            ch = o.get("channels_5min") or {}
            return [f"{o.get('team')}: field tilt {_pct(o.get('field_tilt_5min'))} (5 min), xG {o.get('xg_5min')}",
                    f"Attacks by channel: left {ch.get('left')} · centre {ch.get('centre')} · right {ch.get('right')}"]
        if agent == "passing_network":
            return [f"Top connection: {o.get('top_connection')}", f"Hub player: {o.get('hub_name')}"]
        if agent == "space_analysis":
            return [f"Best overload: {o.get('best_overload')} channel ({o.get('best_overload_situation')})",
                    f"Gap between defensive lines: {o.get('gap_between_lines_m')} m"]
        if agent == "pressing_analysis":
            return [f"{team_name(t)}: PPDA {v.get('ppda_5min')} (5 min), press success {_pct(v.get('press_success_rate'))}, "
                    f"{v.get('high_turnovers_match')} high turnovers" for t, v in o.items() if isinstance(v, dict)]
        if agent == "substitution_impact":
            subs = o.get("substitutions") or []
            return [f"{s['on_name']} on for {s['off_name']} ({s.get('reason') or 'no reason given'}) — {s['status']}" for s in subs[-2:]] or ["No substitutions yet"]
        if agent == "player_intelligence":
            return [f"{p['name']} ({p['position']}, {p['team']}) — influence rank #{p.get('influence_rank')}" for p in (o.get("players") or [])[:3]]
        if agent == "team_intelligence":
            return [f"{v['name']}: possession {_pct(v.get('possession'))}, xG {v.get('xg')}, PPDA {v.get('ppda')}" for v in (o.get("teams") or {}).values()]
        if agent == "mag_memory":
            mems = o.get("memories") or []
            return [f"Recalled {len(mems)} long-term memories"] + [f"• {m['text'][:110]}" for m in mems[:2]]
        if agent == "rag_retrieval":
            docs = o.get("documents") or []
            plan = o.get("plan") or {}
            return [f"Plan: {plan.get('rationale', '')[:140]}", f"{o.get('rounds')} retrieval round(s), quality {o.get('quality')}"] + \
                   [f"• {d['title']} (score {d['rerank_score']})" for d in docs[:3]]
        if agent == "historical_comparison":
            cmp_ = o.get("comparison")
            return [f"Closest precedent: {cmp_['title']}", f"Shared patterns: {', '.join(cmp_.get('shared_patterns') or []) or '–'}"] if cmp_ else ["No sufficiently similar match"]
        if agent == "similar_match":
            ep = o.get("earlier_patterns") or []
            return [f"Earlier in this match: {p['minute']}' {p['team']} {p['type'].replace('_', ' ').lower()}" for p in ep[:2]] or ["No earlier similar moment"]
        if agent == "prediction":
            return [f"{p['label']}: {_pct(p['probability'])} (prediction, not a fact)" for p in (o.get("predictions") or [])[:3]]
        if agent == "expert_analyst":
            ex = o.get("explanations") or {}
            return [f"Azure OpenAI ({o.get('_model') or 'local reasoner'}) · one call writes all 4 knowledge levels",
                    f"Headline: {o.get('headline', '')}", f"Professional: {ex.get('professional', '')[:160]}"]
        if agent == "fact_verification":
            return [f"{len(o.get('verified_claims') or [])} claims verified · {len(o.get('unverified_claims') or [])} rejected",
                    f"Issues: {'; '.join(o.get('issues') or [])[:150] or 'none'}"]
        if agent == "casual_fan_explanation":
            return [f"Beginner: {o.get('beginner', '')[:150]}", f"Jargon replaced: {', '.join(o.get('jargon_replaced') or []) or 'none'}"]
        if agent == "broadcast_commentary":
            return [f"🎙 {o.get('commentary', '')}"]
        if agent == "storytelling":
            return [f"Story beats: {', '.join(o.get('story_beats') or []) or 'none'} · turning point: {o.get('turning_point')}"]
        if agent == "fan_personalization":
            return [f"{team_name(t)} fans: {v}" for t, v in (o.get("perspectives") or {}).items()]
        if agent == "alert":
            return [f"Alert level: {o.get('level')} {('— ' + o['text']) if o.get('text') else ''}"]
        if agent == "visualization_3d":
            cmds = o.get("commands") or []
            kinds = {}
            for c in cmds:
                kinds[c.get("type")] = kinds.get(c.get("type"), 0) + 1
            return [f"{len(cmds)} 3D scene commands: " + ", ".join(f"{k}×{v}" for k, v in kinds.items())]
        if agent == "voice_narrator":
            vs = o.get("voice_scripts") or {}
            return [f"Spoken lines for {len(vs)} personas", f"Kids: {vs.get('kids', '')[:110]}"]
        if agent == "final_answer":
            return [f"Overall confidence {o.get('overall_confidence')} from {o.get('agents_counted')} agents"]
    except Exception:  # noqa: BLE001
        pass
    scal = [f"{k}: {v}" for k, v in o.items() if isinstance(v, (str, int, float)) and not k.startswith("_")]
    return scal[:3] or ["(no output)"]
