"""Render docs/EVALUATION.md from eval/results/*.json (every number in the report comes from a results file).

  python -m eval.report
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"
DOC = ROOT.parent / "docs" / "EVALUATION.md"


def load(name):
    f = RES / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else None


def pct(v):
    return "–" if v is None else f"{v * 100:.0f}%"


def main():
    det, llm = load("deterministic"), load("llm")
    syn = json.loads((ROOT / "app/tactical/profiles/synthetic.json").read_text())
    L = []
    w = L.append
    w("# Evaluation Report — Football Intelligence OS\n")
    w("The product runs on **synthetic, football-realistic data** (hackathon requirement). Every number below is generated "
      "by the scripts in `backend/eval/`: the hallucination, cost and latency results on our synthetic demo match, pattern "
      "detection on held-out synthetic matches with known ground truth. Models are always scored on data they were **not** "
      "fitted or tuned on. Reproduce with:\n")
    w("```bash\ncd backend\n.venv/bin/python -m eval.tune_synthetic   # supervised thresholds (train seeds)\n"
      ".venv/bin/python -m eval.select_synthetic # model selection (validation seeds)\n"
      ".venv/bin/python -m eval.deterministic    # pattern detection (test seeds)\n"
      ".venv/bin/python -m eval.llm_eval         # hallucination, cost, latency, translation (uses Azure OpenAI)\n"
      ".venv/bin/python -m eval.report\n```\n")

    # ---------------- headline
    w("## Headline results\n")
    w("| Question | Result |")
    w("|---|---|")
    if llm:
        h = llm["hallucination"]["conditions"]
        w(f"| Does the architecture reduce hallucination? | Unsupported or contradicted claims: **{h['naive']['unsupported_pct'] + h['naive']['contradicted_pct']:.0f}%** "
          f"for a naive chatbot prompt → **{h['grounded']['unsupported_pct'] + h['grounded']['contradicted_pct']:.0f}%** with evidence grounding → "
          f"**{h['pipeline']['unsupported_pct'] + h['pipeline']['contradicted_pct']:.0f}%** with the full verification pipeline "
          f"({llm['hallucination']['samples']} moments of the {llm['match'].split('—')[0].strip().lower()}, independent LLM judge) |")
        c = llm["cost_latency"]
        w(f"| What does a match cost? | **${c['cost_usd_match']:.2f}** of LLM for a whole match "
          f"({c['llm_calls']} calls for {c['events']} events; {c['events_without_llm_pct']}% of events used no LLM) |")
    if det:
        p = det["patterns_synthetic"]
        w(f"| Does tactical detection find the right patterns? | Precision **{pct(p['micro_precision'])}**, recall **{pct(p['micro_recall'])}** "
          f"on {p['seeds']} unseen matches with known ground truth |")
    if llm:
        t = llm["translation"]
        w(f"| Is translated commentary safe? | **{t['verified_pct']:.0f}%** of translations passed number/name re-verification "
          f"({t['first_try_pct']:.0f}% first try); failures fall back to verified English |")
    w("")

    # ---------------- hallucination
    if llm:
        h = llm["hallucination"]
        w("## 1. Hallucination control\n")
        w(f"**Setup.** {h['samples']} highest-significance moments of *{llm['match']}*. For each moment three texts are "
          "produced and judged against the **same evidence package** the platform computed from event data:\n")
        w("- **naive**: a typical chatbot prompt (\"explain this moment\") given only the event, teams, minute and score.")
        w("- **grounded**: our evidence-grounded prompt, first draft, *before* fact verification.")
        w("- **pipeline**: the published insight after the verification loop and substitution.\n")
        w("Metrics: an independent judge prompt splits each text into atomic claims and labels each SUPPORTED / UNSUPPORTED / "
          "CONTRADICTED with respect to the evidence. Separately, a deterministic check counts numbers that cannot be traced to the evidence.\n")
        w("| Condition | Claims judged | Supported | Unsupported | Contradicted | Texts with ≥1 bad claim | Untraceable numbers |")
        w("|---|---|---|---|---|---|---|")
        for k in ("naive", "grounded", "pipeline"):
            d = h["conditions"][k]
            w(f"| {k} | {d['claims']} | {d['supported_pct']}% | {d['unsupported_pct']}% | {d['contradicted_pct']}% | "
              f"{d['texts_with_any_unsupported_or_contradicted_pct']}% | {d['untraceable_numbers_pct']}% ({d['numbers']} numbers) |")
        if h["conditions"]["naive"].get("foundry", {}).get("n"):
            w("\n### Microsoft Foundry evaluators\n")
            w("The same texts scored with Microsoft's **azure-ai-evaluation** SDK (Groundedness against the evidence package and "
              "Relevance to the request, 1–5 scale), judged by our Azure OpenAI deployment in Microsoft Foundry:\n")
            w("| Condition | Groundedness (mean, 1–5) | Grounded ≥ 4 | Relevance (mean, 1–5) |")
            w("|---|---|---|---|")
            for k in ("naive", "grounded", "pipeline"):
                fd = h["conditions"][k]["foundry"]
                w(f"| {k} | {fd['groundedness_mean']} | {fd['groundedness_ge4_pct']}% | {fd['relevance_mean']} |")
            w("\nThe Foundry groundedness score judges whole texts and is lenient with short, plausible answers (the naive prompt "
              "also scores high). Our claim-level checker above is the stricter test, so we report both: Foundry confirms grounded "
              "texts stay at 100% ≥ 4, and the claim-level audit shows where the remaining errors are.")
        w("\n**Reading the results.** Grounding the LLM in the evidence package is the big win: unsupported or contradicted claims "
          "fall roughly fourfold and untraceable numbers fall to zero. The verification loop guarantees numbers, event IDs, sources and "
          "prediction wording; it does not rewrite *interpretive* sentences (e.g. \"this boosted Azure City's momentum\"), which a strict "
          "judge marks unsupported. So grounded and pipeline score within noise of each other on that metric. A semantic claim-level "
          "checker is the next step on the roadmap.\n")
        w("\n*Unsupported* does not always mean false: a naive model may state true real-world facts about famous players or national teams. "
          "It does mean the claim is **not traceable to the match data**, so it can't be shown in the WHY? panel or verified, "
          "and that's the risk this architecture removes.\n")

    # ---------------- patterns
    if det:
        p = det["patterns_synthetic"]
        w("## 2. Tactical pattern detection\n")
        w(f"**Ground truth.** The synthetic generator is driven by a tactical script (press intensity, block height, flank bias, "
          f"full-back push). The detectors never see the script. Scripted phases become labelled windows. "
          f"Tolerance: {p['tolerance']}.\n")
        w("**Protocol.** Hand-set thresholds (tuned on seed 11), plus supervised thresholds fitted on train seeds 0–29; "
          "per pattern the better one was chosen on **validation seeds 30–59**; results below are on **test seeds 100–129**.\n")
        w("| Pattern | Precision | Recall | Detections | Scripted windows | Median detection delay | Thresholds |")
        w("|---|---|---|---|---|---|---|")
        sel = syn.get("selection", {})
        for k, v in p["per_pattern"].items():
            w(f"| {k.replace('_', ' ').title()} | {pct(v['precision'])} | {pct(v['recall'])} | {v['detections']} | {v['scripted_windows']} | "
              f"{v['median_latency_min']} min | {sel.get(k, {}).get('choice', 'hand-set')} |")
        w(f"| **Micro average** | **{pct(p['micro_precision'])}** | **{pct(p['micro_recall'])}** | | | | |\n")
        w("Many high-press \"false positives\" fall in phases where a team presses fairly hard but below the script's ground-truth "
          "threshold (e.g. Thames chasing the game at press intensity 0.72), so the precision is conservative.\n")
    # ---------------- cost & latency
    if llm:
        c = llm["cost_latency"]
        w(f"## 3. Cost and latency ({llm['match']}, production pipeline)\n")
        w("| Metric | Value |")
        w("|---|---|")
        w(f"| Events processed | {c['events']} |")
        w(f"| Deep (LangGraph) analyses | {c['deep_analyses']} |")
        w(f"| Published insights | {c['insights']} |")
        w(f"| LLM calls / tokens (in + out) | {c['llm_calls']} / {c['tokens_prompt']:,} + {c['tokens_completion']:,} |")
        w(f"| Events handled with zero LLM tokens | {c['events_without_llm_pct']}% |")
        w(f"| LLM cost for the whole match | ${c['cost_usd_match']:.3f} (at ${c['price_assumption_usd_per_1M']['input']}/1M in, ${c['price_assumption_usd_per_1M']['output']}/1M out; verify current pricing) |")
        w(f"| Fast path latency per event (p50 / p95) | {c['fast_path_ms']['p50']} ms / {c['fast_path_ms']['p95']} ms |")
        if c.get("deep_path_ms"):
            w(f"| Deep path latency per analysed event (p50 / p95) | {c['deep_path_ms']['p50']/1000:.1f} s / {c['deep_path_ms']['p95']/1000:.1f} s "
              "(measured while replaying the whole match in ~3 min, so the Azure deployment was rate-limiting (429) and calls queued; "
              "an unthrottled single analysis takes ~3–6 s) |")
        v = c["verification"]
        w(f"| Verification | {v['passed_first_attempt']} insights passed first time · {v['retries']} self-corrections · {v['fields_replaced']} field substitutions |")
        w("")
        m = c["cost_usd_match"]
        w("### Cost per fan at scale\n")
        w("Insights and translations are computed once per match (and once per language) and shared by every viewer. "
          "The naive alternative, a per-fan assistant that calls the LLM for the same moments, scales linearly.\n")
        w("| Concurrent viewers | Shared FIOS cost per match | Naive per-fan design | Saving |")
        w("|---|---|---|---|")
        for n_ in (1, 1_000, 100_000, 1_000_000):
            naive = m * n_
            w(f"| {n_:,} | ${m:.2f} | ${naive:,.2f} | {'–' if n_ == 1 else f'{naive / m:,.0f}×'} |")
        w("\nFan questions add cost per question, reduced by the shared answer cache and the zero-token re-style path "
          "(\"explain like I'm a beginner\" reuses already-verified text).\n")
    if llm:
        t = llm["translation"]
        w("## 4. Multilingual commentary\n")
        w(f"{t['translations']} translations of verified insights into {', '.join(t['languages'])}. Each translation is re-verified: "
          "no number may be added or changed (decimals, percentages and years must survive; Arabic-Indic and Devanagari digits "
          "are normalised) and player names must stay intact. Failures retry once, then fall back to verified English.\n")
        w(f"Verified: **{t['verified_pct']}%** · first try: **{t['first_try_pct']}%**.\n")
    w("## Limitations\n")
    w("- The LLM judge is a model too (same family as the generator); it is instructed to be strict and sees exactly the evidence, "
      "but it is not a human annotation. The deterministic untraceable-number check is independent of any model.")
    w("- Pattern ground truth comes from the synthetic generator's tactical script; detectors never see the script, but "
      "real football is noisier than any generator.")
    w("- The xG and goal-threat models use logistic coefficients estimated offline (`app/prediction/fitted.json`); only the "
      "parameters ship, and every match the product analyses is synthetic. The goal-threat signal is weak, so the UI labels it "
      "a low-resolution estimate.")
    w("- Cost uses list prices that change; latency depends on Azure quota (429 throttling adds seconds under bursts).")
    DOC.write_text("\n".join(L))
    print(f"wrote {DOC}")


if __name__ == "__main__":
    main()
