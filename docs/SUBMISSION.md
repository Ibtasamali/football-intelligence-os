# Submission Kit — Inside the Game: Developer Hackathon

## 1. Project name and tagline
**Football Intelligence OS**: *Every match. Every moment. Explained by AI.*

## 2. Elevator pitch (paste into the "Project Pitch / Description" field)

Football data feeds produce thousands of events per match, but fans, studios and broadcasters get the *what*, not the
*why*, and generic chatbots invent statistics. **Football Intelligence OS** turns a stream of **synthetic,
football-realistic match events** into explainable, real-time match intelligence.

A LangGraph orchestrator routes each event to **30 specialised agents** (perception, tactics, knowledge, reasoning,
experience). Most events stay on a zero-token fast path; significant moments trigger agentic RAG, short-term context
(CAG) and long-term memory (MAG), then **Azure OpenAI (Microsoft Foundry)** writes one explanation at four knowledge
levels. A **Fact Verification agent** checks every number, event and source before anything is published, and every
insight has a **Why?** panel with its evidence.

Fans get a live 3D tactical view, a **What-if lab** (drag a player; a pitch-control model recomputes space and danger),
hands-free **voice conversation**, and commentary in **14 languages** with native **Azure AI Speech** voices.
Translations are re-verified so numbers can never change. Blind and low-vision fans get an **Accessibility mode**
with live audio description and keyboard control. Studios get a **Recap Studio** (social post, push, lower-third,
newsletter and a two-host podcast in one click, all verified), match stories and an agent control center with full
traceability. A **Microsoft Agent Framework performance desk** produces a verified coach report and PDF through four
explicit handoffs. A metadata-only **OpenTelemetry trace waterfall** also exports to Application Insights. Developers
can call the platform as an **A2A agent** or from **GitHub Copilot through an MCP server**.

**Microsoft / Azure:** Azure OpenAI in Microsoft Foundry (gpt-4.1-mini, tiered model routing, JSON-mode structured
output), Azure AI Speech (neural TTS in 14 languages, STT), Azure AI Document Intelligence (scouting reports into RAG),
designed for Azure Container Apps, Azure Cosmos DB for MongoDB vCore (vector search), Azure Cache for Redis, Azure Web
PubSub, Key Vault, Application Insights and Entra ID (Bicep included).

**Impact:** about $0.05 of LLM per match; 99% of events never touch an LLM; unsupported claims cut from 58% to 11%; Microsoft Foundry groundedness ≥ 4 on 100% of pipeline answers; one verified insight is
shared by every viewer and language. See `docs/EVALUATION.md`.

## 3. Two-minute video (rule: < 2:00, show it running, no third-party trademarks or copyrighted music)

**How to record:** run `PREPARE DEMO.command` once, open the app in Chrome full screen, start macOS screen recording
(**Cmd + Shift + 5 → Record Entire Screen**, with "Options → Microphone" if you narrate), then click **🎬 2-min video**.
It runs on its own in about 1:50. Stop recording and trim the start. A machine-recorded fallback is in
`docs/video/fios-2min-v3.mp4` (1:48) and the full walkthrough in `docs/video/fios-full-v3.mp4` (6:52). Upload to **YouTube (Unlisted or Public)** and paste
the link.

| Time | What plays automatically | Optional voice-over |
|---|---|---|
| 0:00 | Synthetic match starts, 3D stadium | "Every pass, press and shot is an event. Most cost zero tokens." |
| 0:10 | *High press* / *flank overload* detected | "Thirty agents, orchestrated by LangGraph, detect tactics from the data alone." |
| 0:28 | Goal, then **Why?** panel | "Every claim is verified against events and numbers. No hallucinated stats." |
| 0:33 | Cards switch to Urdu | "Fourteen languages, re-verified after translation, native Azure voices." |
| 0:36 | Copilot answers "Why did Thames Athletic score?" | "Fans just ask: memory, retrieval and reasoning through Azure OpenAI in Foundry." |
| 0:49 | **What-if lab** moves a defender | "Move a player and a pitch-control model recomputes the danger." |
| 0:57 | Late counter-attack: the AI flags it, then the goal | "It saw the counter coming." |
| 1:12 | Match story | "Thousands of events become a verified story, for about five cents." |
| 1:22 | **Recap Studio** | "One click: lower-third, social post, push, newsletter and a two-host podcast." |
| 1:28 | **Coach report** (Microsoft Agent Framework) | "An Agent Framework desk writes a verified coach report and PDF." |
| 1:32 | **Traces** (OpenTelemetry) | "Every agent handoff is observable in production." |
| 1:38 | **Accessibility mode** | "Built for every fan, including blind and low-vision supporters." |
| 1:44 | End card | "Football Intelligence OS. Every match, every moment, explained by AI." |

No copyrighted music. All club and player names are fictional (synthetic data). Don't show real club logos or league
branding.

## 4. Categories to target
| Category | Our evidence |
|---|---|
| **Grand Prize** | Complete end-to-end product; explainable intelligence; personalisation; measured evaluation |
| **Best Multi-Agent Orchestration** | 30 agents with distinct roles and conditional LangGraph routing, plus a real **Microsoft Agent Framework** workflow (evidence analyst → coach strategist → verifier → PDF publisher); retries and failure recovery; **A2A 0.3 + 1.0**; **MCP server** used by GitHub Copilot agent mode |
| **Best Use of Microsoft Foundry** | Azure OpenAI deployment in Foundry with tiered routing, structured output, cached responses; **Foundry evaluators** (azure-ai-evaluation groundedness + relevance) in the evaluation harness |
| **Best Enterprise Solution** | Recap Studio; verified coach PDF; first-time judge tour; accessibility mode; provenance on every insight; tenant isolation, auth, rate limiting, audit logs, Key Vault; OpenTelemetry waterfall + Application Insights; tests |

## 5. Checklist before submitting (deadline October 27)
- [ ] **Rotate the Azure keys** that were shared in chat; put the new ones only in `backend/.env` (gitignored).
- [x] **Public GitHub repository**: https://github.com/Ibtasamali/football-intelligence-os
- [ ] Record and upload the **< 2-minute video** (above). Check it is under 2:00.
- [ ] Paste the **pitch** (section 2), the video URL and the GitHub URL on the project page.
- [ ] Optional: deploy to **Azure Container Apps** for a live URL (`infra/azure/deploy.sh`).
- [ ] Make sure the app runs on **synthetic data only** (default; `ENABLE_REAL_DATA=false`).
