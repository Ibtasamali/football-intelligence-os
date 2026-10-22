"""LLM evaluations on the product's own SYNTHETIC demo match.

1. Cost & latency: full replay through the production pipeline (fast path + LangGraph deep path).
2. Hallucination: for each significant moment, three conditions judged against the SAME evidence package —
     naive    : a typical chatbot prompt with only the event description (no evidence, no rules)
     grounded : our evidence-grounded prompt, first draft, before verification
     pipeline : the published insight (verification loop + substitution)
   Metrics: (a) untraceable numbers (deterministic: number not present in the evidence),
            (b) an independent LLM judge labelling every atomic factual claim SUPPORTED / UNSUPPORTED / CONTRADICTED.
3. Translation: verified-translation pass rates for 3 languages.

  python -m eval.llm_eval   → eval/results/llm.json
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import numpy as np

from app.agents.evidence import NUM_RE, _number_ok, allowed_numbers
from app.core.config import get_settings
from app.data.teams import player_name, team_name
from app.services.container import Container
from app.services.observability import OBS

OUT = Path(__file__).parent / "results"
PRICE_IN, PRICE_OUT = 0.40, 1.60  # USD per 1M tokens, gpt-4.1-mini list price at time of writing — verify for your region

NAIVE_SYSTEM = "You are an expert football TV analyst. Explain this moment to fans in 3–4 sentences: what happened, why it matters, and what it means tactically."
JUDGE_SYSTEM = """You are a strict fact-checking judge for football commentary.
Given EVIDENCE (the only trusted facts about this match) and a TEXT, split the TEXT into atomic factual claims about this
match (events, numbers, players, tactics, history). Ignore pure opinion and generic football definitions.
Label each claim:
  SUPPORTED     – directly stated in or computable from EVIDENCE
  UNSUPPORTED   – not in EVIDENCE (even if it might be true in the real world)
  CONTRADICTED  – conflicts with EVIDENCE
Return JSON: {"claims": [{"claim": "...", "label": "SUPPORTED|UNSUPPORTED|CONTRADICTED"}]}"""


def foundry_evaluators(settings):
    """Microsoft Foundry evaluators (azure-ai-evaluation): Groundedness + Relevance, judged by our Foundry deployment."""
    try:
        from azure.ai.evaluation import AzureOpenAIModelConfiguration, GroundednessEvaluator, RelevanceEvaluator
    except ImportError:
        return None
    cfg = AzureOpenAIModelConfiguration(azure_endpoint=settings.azure_openai_endpoint, api_key=settings.azure_openai_api_key,
                                        azure_deployment=settings.azure_openai_deployment, api_version=settings.azure_openai_api_version)
    return GroundednessEvaluator(cfg), RelevanceEvaluator(cfg)


def run_foundry(evs, query: str, context: str, response: str) -> dict:
    g, r = evs
    try:
        gs = g(query=query, context=context, response=response).get("groundedness")
        rs = r(query=query, response=response).get("relevance")
        return {"groundedness": float(gs) if gs is not None else None, "relevance": float(rs) if rs is not None else None}
    except Exception as exc:  # noqa: BLE001
        return {"groundedness": None, "relevance": None, "error": str(exc)[:120]}


def untraceable(text: str, evidence: dict) -> tuple[int, int]:
    allowed = allowed_numbers(evidence)
    nums = [float(n) for n in NUM_RE.findall(text or "")]
    return sum(1 for n in nums if not _number_ok(n, allowed)), len(nums)


async def judge(c, evidence: dict, text: str) -> dict:
    ev = {k: v for k, v in evidence.items() if k not in ("metrics", "valid_event_ids")}
    res = await c.llm.complete_json(system=JUDGE_SYSTEM, user="EVIDENCE:\n" + json.dumps(ev, default=str)[:9000] + "\n\nTEXT:\n" + text,
                                    tier="small", fallback=lambda: {"claims": []}, max_tokens=900, temperature=0, interactive=True)
    labels = [cl.get("label", "").upper() for cl in res.data.get("claims", []) if isinstance(cl, dict)]
    return {"n": len(labels), "supported": labels.count("SUPPORTED"), "unsupported": labels.count("UNSUPPORTED"),
            "contradicted": labels.count("CONTRADICTED"), "judge_failed": res.fallback}


async def main(max_samples: int = 18):
    s = get_settings()
    c = Container(s)
    await c.start(use_mock_db=True, use_memory_kv=True, enable_llm=True)
    c.eval_mode = True
    from app.data.synthetic import generate_demo_match
    from app.data.teams import AWAY_ID, HOME_ID
    from app.models.domain import Match
    cur = {"label": "Synthetic demo match — Azure City FC vs Thames Athletic"}
    match = Match(match_id="eval-final", home_team_id=HOME_ID, away_team_id=AWAY_ID, competition="Showcase League (synthetic)",
                  venue="Azure Arena", kickoff="synthetic", score={HOME_ID: 0, AWAY_ID: 0})
    events = generate_demo_match("eval-final")
    rt = await c.create_match(match)

    # ---------------- 1. cost & latency
    fast = []
    t0 = time.time()
    for e in events:
        a = time.perf_counter()
        await c.ingest(e, persist=False)
        fast.append((time.perf_counter() - a) * 1000)
        await asyncio.sleep(0.004)
    await c.pool.drain(1800)
    wall = time.time() - t0
    runs = await c.db.find("agent_runs", {"match_id": "eval-final"})
    durs = [r["duration_ms"] for r in runs if not r.get("cache_hit")]
    cn = dict(OBS.counters)
    tok_in, tok_out = cn.get("tokens_prompt", 0), cn.get("tokens_completion", 0)
    cost = (tok_in * PRICE_IN + tok_out * PRICE_OUT) / 1e6
    ins_all = [i for i in rt.insights]
    verified_first = sum(1 for i in ins_all if i.verification.get("attempts") == 1 and i.verification.get("passed"))
    cost_res = {
        "events": len(events), "deep_analyses": int(cn.get("events_analysed", 0)), "insights": len(ins_all),
        "llm_calls": int(cn.get("llm_calls", 0)), "tokens_prompt": int(tok_in), "tokens_completion": int(tok_out),
        "events_without_llm_pct": round(100 * (1 - cn.get("llm_calls", 0) / len(events)), 2),
        "cost_usd_match": round(cost, 4), "price_assumption_usd_per_1M": {"input": PRICE_IN, "output": PRICE_OUT},
        "fast_path_ms": {"p50": round(float(np.percentile(fast, 50)), 2), "p95": round(float(np.percentile(fast, 95)), 2)},
        "deep_path_ms": {"p50": round(float(np.percentile(durs, 50))), "p95": round(float(np.percentile(durs, 95)))} if durs else None,
        "verification": {"passed_first_attempt": verified_first, "retries": int(cn.get("verification_retries", 0)),
                         "fields_replaced": int(cn.get("claims_replaced_after_verification", 0)),
                         "llm_fallbacks": int(cn.get("llm_failures", 0))},
        "wall_clock_s": round(wall, 1),
    }
    print("COST", json.dumps(cost_res, indent=1))

    # ---------------- 2. hallucination comparison
    samples = sorted([i for i in ins_all if i.statistics.get("first_draft") and i.statistics.get("evidence")
                      and i.provenance.model.startswith("gpt")], key=lambda i: -i.significance)[:max_samples]
    rows = []
    fevs = foundry_evaluators(s) if s.llm_enabled else None
    for ins in samples:
        evd = ins.statistics["evidence"]
        ev = rt.engine.by_id.get(ins.event_id)
        score = evd["match"]["score_text"]
        desc = (f"{team_name(match.home_team_id)} vs {team_name(match.away_team_id)}, {match.competition}. "
                f"Minute {ev.clock if ev else ins.minute}. Score now: {score}. Event: {ev.type.value if ev else ins.category} "
                f"by {player_name(ev.player_id) if ev and ev.player_id else 'unknown'} ({team_name(ev.team_id) if ev else ''}).")
        naive = await c.llm.complete_json(system=NAIVE_SYSTEM + ' Return JSON {"text": "..."}', user=desc, tier="small",
                                          fallback=lambda: {"text": ""}, max_tokens=400, temperature=0.4, interactive=True)
        fd = ins.statistics["first_draft"]
        texts = {"naive": naive.data.get("text", ""),
                 "grounded": f"{fd.get('headline', '')}. {(fd.get('explanations') or {}).get('professional', '')}",
                 "pipeline": f"{ins.headline}. {ins.explanations.get('professional', '')}"}
        row = {"insight_id": ins.insight_id, "minute": ins.minute, "category": ins.category}
        ctx_txt = json.dumps({k: v for k, v in evd.items() if k not in ("metrics", "valid_event_ids")}, default=str)[:7000]
        for cond, text in texts.items():
            bad, total = untraceable(text, evd)
            row[cond] = {"untraceable_numbers": bad, "numbers": total, "judge": await judge(c, evd, text), "chars": len(text),
                         "text": text[:600]}
            if fevs:
                row[cond]["foundry"] = await asyncio.to_thread(run_foundry, fevs, "Explain this football match moment: " + desc, ctx_txt, text)
        rows.append(row)
        print(row["minute"], row["category"], {k: (row[k]["judge"]["unsupported"], row[k]["judge"]["contradicted"], row[k]["judge"]["n"]) for k in texts})

    def agg(cond):
        J = [r[cond]["judge"] for r in rows if not r[cond]["judge"]["judge_failed"]]
        n = sum(j["n"] for j in J) or 1
        nums = sum(r[cond]["numbers"] for r in rows) or 1
        F = [r[cond].get("foundry") or {} for r in rows]
        gs = [f["groundedness"] for f in F if f.get("groundedness") is not None]
        rs = [f["relevance"] for f in F if f.get("relevance") is not None]
        foundry = {"groundedness_mean": round(float(np.mean(gs)), 2) if gs else None,
                   "groundedness_ge4_pct": round(100 * float(np.mean([g >= 4 for g in gs])), 1) if gs else None,
                   "relevance_mean": round(float(np.mean(rs)), 2) if rs else None, "n": len(gs)}
        return {"foundry": foundry, "claims": sum(j["n"] for j in J), "supported_pct": round(100 * sum(j["supported"] for j in J) / n, 1),
                "unsupported_pct": round(100 * sum(j["unsupported"] for j in J) / n, 1),
                "contradicted_pct": round(100 * sum(j["contradicted"] for j in J) / n, 1),
                "texts_with_any_unsupported_or_contradicted_pct": round(100 * np.mean([(j["unsupported"] + j["contradicted"]) > 0 for j in J]), 1),
                "numbers": sum(r[cond]["numbers"] for r in rows),
                "untraceable_numbers_pct": round(100 * sum(r[cond]["untraceable_numbers"] for r in rows) / nums, 1)}
    halluc = {"samples": len(rows), "conditions": {k: agg(k) for k in ("naive", "grounded", "pipeline")}, "rows": rows}
    print("HALLUCINATION", json.dumps(halluc["conditions"], indent=1))

    # ---------------- 3. translation reliability
    tr_rows = []
    for ins in samples[:8]:
        for lang in ("es", "ar", "hi"):
            before = OBS.counters.get("translation_retries", 0)
            out = await c.localize(ins.model_dump(), lang, "intermediate", "casual_commentator")
            tr_rows.append({"lang": lang, "verified": out["localized"]["verified"],
                            "retried": OBS.counters.get("translation_retries", 0) > before})
    trans = {"translations": len(tr_rows), "verified_pct": round(100 * np.mean([r["verified"] for r in tr_rows]), 1),
             "first_try_pct": round(100 * np.mean([r["verified"] and not r["retried"] for r in tr_rows]), 1),
             "languages": ["es", "ar", "hi"]}
    print("TRANSLATION", trans)
    OUT.mkdir(exist_ok=True)
    (OUT / "llm.json").write_text(json.dumps({"match": cur["label"], "cost_latency": cost_res, "hallucination": halluc,
                                              "translation": trans}, indent=2, default=str))
    await c.stop()


if __name__ == "__main__":
    asyncio.run(main())
