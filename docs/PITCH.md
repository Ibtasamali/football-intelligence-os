# Pitch Deck — Football Intelligence OS

**1 · Title**
Football Intelligence OS — *Every Match. Every Moment. Explained by AI.*

**2 · The problem**
Fans and analysts get *what* happened (scores, stats, highlight clips) but not *why*. Data feeds produce
thousands of events per match; nobody can read them live. Commentary is one-size-fits-all: too shallow for
analysts, too technical for new fans. And generic AI chatbots invent stats.

**3 · The product**
A live AI layer over any match: it watches every event, detects tactical patterns, explains cause and effect,
predicts what's next, and shows it in 3D, by voice, at the fan's level. Every claim links to its evidence.

**4 · Demo moment**
On a synthetic, football-realistic match the system flags *Thames overloading the right flank (77% of attacking-half
actions)* at 28', and the goal comes from that flank at 34'. Late on it flags *Thames exposed in transition* at 82',
a minute before the 83' counter-attack goal. Click **Why?**: events, metrics and verified claims. Switch to Urdu or
Arabic and a native voice reads the re-verified translation. Drag a defender in the **What-if lab** and watch the danger change.

**5 · How it works: agentic, not a chatbot**
LangGraph state machine with conditional edges and 30 specialized agents. A router picks agents, parallel
waves, memory, retrieval and model tier per event. CAG (live context cache), MAG (long-term + fan memory) and
Agentic RAG (plan → retrieve → rerank → validate → re-plan).

**6 · Trust: measured, not claimed**
Unsupported or contradicted claims fall from **58%** (a naive chatbot prompt) to **11%**, Microsoft Foundry groundedness is ≥ 4 on **100%** of texts, and
untraceable numbers stay at **0%**. Pattern detection reaches 63% precision and 77% recall on unseen matches with known
ground truth. The evaluation even caught our own over-confident goal predictor, so we refit it and labelled it honestly.

**6b · How trust is built**
Numbers come from a deterministic tactical engine. The LLM only reasons over an evidence package. The Fact
Verification agent rejects unknown events, untraceable numbers, unretrieved matches and predictions stated
as certainty. It retries once with feedback, then substitutes grounded text. Low confidence returns
"I don't have enough evidence."

**7 · Cost and scale**
About **$0.05 of LLM per match**; 99% of events use zero tokens. One LLM call writes all four explanation levels and every voice script,
shared by every fan. Shared insight, answer and LLM caches mean 100 fans asking the same question cost one call.
Stateless workers on Azure Container Apps, with Web PubSub fan-out: an elastic agentic architecture
capable of orchestrating millions of AI tasks.

**8 · Microsoft stack**
Azure OpenAI / Foundry (tiered models), AI Speech (persona voices), Document Intelligence (scouting reports into RAG),
Cosmos DB for MongoDB vCore (data and vectors), Redis (CAG), Web PubSub, Container Apps, Key Vault, App Insights, Entra ID.

**8b · Open agent ecosystem**
Two frameworks, one verified brain: the 30-agent LangGraph platform is exposed as an **A2A agent** (agent card +
JSON-RPC, protocol 0.3 and 1.0) and as an **MCP server** that GitHub Copilot uses directly. A **Microsoft Agent
Framework** workflow (evidence analyst → coach strategist → claim verifier → PDF publisher) produces a verified
**coach report PDF**. Every run, from a LangGraph node to a single Azure OpenAI call, is an **OpenTelemetry** span
on the in-app Traces screen and in Application Insights; prompts are never stored.

**9 · Personalization**
Beginner: "Your team won the ball back quickly and attacked straight away." Professional: "PPDA 2.45 over
5 minutes, 19 pressures in the opponent half…" Same verified facts, the fan's favourite-team perspective,
and a voice persona from Kids mode to Expert analyst.

**10 · Business**
B2B2C: broadcasters (second-screen and auto-commentary in many languages), clubs (opposition analysis, with
reports ingested via Document Intelligence), betting and fantasy (explainable, labelled probabilities), leagues
(fan engagement). Pricing per match or per active fan; cost per fan approaches zero thanks to shared insights.

**11 · Roadmap**
Real provider feeds (Opta / StatsBomb adapters on the same event schema) · tracking-data pitch control ·
highlight-clip alignment · live tactical alerts on the bench · Foundry Agent Service hosting for the desk.

**12 · Ask**
Pilot with one broadcaster and one club next season.
