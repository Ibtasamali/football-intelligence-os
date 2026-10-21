# Demo Guide

All demos run on **synthetic, football-realistic data**: *Azure City FC vs Thames Athletic* (fictional clubs).

## Before presenting (once)
1. Double-click **`START FOOTBALL AI.command`**. It starts everything and opens the browser.
2. Double-click **`PREPARE DEMO.command`** (~3–5 min). Every insight, the story and the key translations are cached for
   7 days, so the live demo is instant and costs 0 tokens.

## Option A: one click (recommended)
Press **✦ Auto Demo** (about 4 min) or **🎬 2-min video** (about 1:55, for the submission video). It plays on its own
with captions and narration; **■ Stop demo** hands control back to you.

| Step | What happens | Story |
|---|---|---|
| 1–2 | Match starts; routine events stay on the zero-token fast path | "Most events cost nothing" |
| 3 | Azure City's **high press** detected (≈17') | Patterns found from data alone |
| 4 | Thames **overload the right flank** (≈28') → goal from that flank (34') | Pattern → goal |
| 5 | **Why?** panel: verified claims, source events, retrieved history, LangGraph path | No hallucinated stats |
| 6 | Cards switch to **Urdu** | 14 languages, re-verified translation |
| 7 | Copilot: "Why did Thames Athletic score?" (+ "explain like I'm a beginner", zero tokens) | Agentic Q&A |
| 8 | **What-if lab** pushes a defender up; danger recomputed and explained | Pitch-control model |
| 9 | AI flags **Thames exposed in transition** (≈82') → counter-attack goal (83') | It saw it coming |
| 10 | Agent Control Center, then the **Match Story** | Traceability + storytelling |

## Option B: drive it yourself
- **START MATCH**, then use **Jump to…** (15' press era · 26' flank overload · 56' second press · 67' deep block · 78' late drama).
- Click **Why?** on any card, **Replay 3D** to see the sequence, 🌐 to change language.
- **What-if** (top of the pitch): drag any player and read the before → after numbers.
- Glowing button → **Start live conversation (hands-free)** and let a judge just talk (Chrome, allow the microphone).

**If Azure is slow or offline:** the platform keeps running on the grounded local reasoner and browser voice.

## New features (2 extra minutes)
1. The **60-second judge tour** opens on the first visit; press `?` in the top bar to replay it.
2. **Coach** → **Generate report**: show the four Microsoft Agent Framework handoffs, verified recommendations and download the PDF.
3. **Traces**: select the newest trace and show the OpenTelemetry waterfall, p50/p95 and privacy badge.
4. **Studio** → pick a language → **Generate recap**: lower-third, social post, push, newsletter, two-host podcast.
5. **♿** → *Enable accessibility mode* → press `D` to hear the pitch described, `P` to play/pause.
6. **A2A**: `cd backend && .venv/bin/python scripts/a2a_client.py "Why did Azure City FC equalise?"`
7. **GitHub Copilot (MCP)**: VS Code → Copilot Chat in *Agent* mode → ask "Use football-intelligence-os to explain the latest insight".
