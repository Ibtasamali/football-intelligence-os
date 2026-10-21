/**
 * Auto Demo: plays the whole judge demo hands-free on the synthetic demo match.
 * Every step waits for the real system (no canned output) and has a timeout, so a slow LLM call
 * never stalls the presentation — the demo simply moves on.
 */
import { api } from "./api";
import { switchMatch } from "./live";
import { useStore } from "./store";
import { prefetch } from "./prefetch";
import { fetchRecap } from "../screens/RecapScreen";
import { speak, stopSpeaking } from "./voice";
import { enterWhatIf, exitWhatIf, movePlayer, runWhatIf } from "./whatif";

const S = () => useStore.getState();
let token = 0;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clockMin = () => {
  const [m, s] = (S().clock || "0:0").split(":").map(Number);
  return m + s / 60;
};

async function waitFor(cond: () => boolean, timeoutMs: number, my: number): Promise<boolean> {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (my !== token) throw new Error("stopped");
    if (cond()) return true;
    await sleep(300);
  }
  return false;
}

function caption(step: number, total: number, text: string, sub?: string, narrate = true) {
  S().set({ demo: { running: true, step, total, caption: text, sub } });
  if (narrate) speak(text, "tactical_analyst");
}

async function jumpTo(labelPart: string, fast = false) {
  const s = S();
  const j = s.jumpPoints.find((x) => x.label.includes(labelPart));
  if (j) s.set({ replay: await api.jump(s.matchId, j.minute, j.seq) });
  if (fast) s.set({ replay: await api.speed(s.matchId, 60, false) });
  s.set({ replay: await api.replay(s.matchId, "start") });
}

export function stopDemo() {
  token++;
  stopSpeaking();
  exitWhatIf();
  S().set({ demo: null, whyId: null });
}

/** short = the < 2-minute cut for the submission video (faster replay, shorter holds, fewer steps). */
export async function runDemo(short = false) {
  const my = ++token;
  const TOTAL = short ? 15 : 20;
  const hold = (ms: number) => sleep(short ? Math.round(ms * 0.32) : ms);
  try {
    // 1 — set the stage
    caption(1, TOTAL, "A synthetic, football-realistic match. Every pass, press and shot is an event.", "Azure City FC vs Thames Athletic · 22 tracked players");
    S().set({ screen: "live", voiceOpen: false, whyId: null, profile: { ...S().profile, language: "en" } });
    const cur = S().matchId;  // keep a separate synthetic match (e.g. the video recorder's) instead of hijacking live-demo
    await switchMatch(S().match?.source === "synthetic" && cur !== "live-demo" ? cur : "demo", "synthetic");
    await sleep(short ? 800 : 2000);
    S().set({ replay: await api.speed(S().matchId, short ? 60 : 20, !short) });
    if (short) S().set({ replay: await api.jump(S().matchId, 15) });  // video cut: start just before the first pattern
    S().set({ replay: await api.replay(S().matchId, "start") });

    // 2 — the AI watches every event
    caption(2, TOTAL, "Routine plays cost zero tokens. The agents wake up only when something matters.", "Fast path → significance → LangGraph router");
    await waitFor(() => S().insights.some((i) => i.patterns?.length), short ? 25000 : 50000, my);

    // 3 — a tactical pattern found from data alone
    const pat = [...S().insights].reverse().find((i) => i.patterns?.length);
    if (pat) S().focusInsight(pat);
    caption(3, TOTAL, "Tactical patterns are detected from the data alone.", pat?.headline);
    await hold(6000);

    // 4 — the right-flank overload becomes a goal
    await jumpTo("26'", short);
    caption(4, TOTAL, "Thames overload the right flank. Watch it turn into a goal.", "Pattern → goal, explained with evidence");
    await waitFor(() => S().insights.some((i) => i.category === "GOAL"), short ? 25000 : 70000, my);
    const goal = S().insights.find((i) => i.category === "GOAL");
    S().set({ replay: await api.replay(S().matchId, "pause") });
    if (goal) {
      S().focusInsight(goal);
      await hold(2500);
      S().set({ whyId: goal.insight_id });
      caption(5, TOTAL, "Why? Every claim is checked against real events and numbers.", "Verified claims · source events · retrieved history · LangGraph path");
      await hold(9000);
      S().set({ whyId: null });
      if (!short) {
        // 5b — open the machine: every agent for this goal, step by step
        S().set({ screen: "pipeline" });
        caption(6, TOTAL, "Inside the agents: the same goal, step by step through the LangGraph.", "Router → analysis waves → memory → RAG → LLM → verification → experience", false);
        const done = S().pipelineDoneAt;
        S().set({ pipelineRequest: { insightId: goal.insight_id, at: Date.now(), speed: 1.15 } });
        await waitFor(() => S().pipelineDoneAt > done, 240000, my);
        await sleep(2500);
        S().set({ screen: "live" });
      }
    }

    // 6 — multilingual
    S().set({ profile: { ...S().profile, language: "ur" } });
    caption(short ? 6 : 7, TOTAL, "Fourteen languages. Translated after fact-checking, numbers re-verified.", "اردو · العربية · Español · हिन्दी …");
    await hold(9000);
    S().set({ profile: { ...S().profile, language: "en" } });

    // 7 — ask the copilot
    caption(short ? 7 : 8, TOTAL, "Fans can just ask.", "“Why did Thames Athletic score?” → agents, memory, retrieval, verification", false);
    let t = S().copilotAnsweredAt;
    const shown = S().copilotShownAt;
    S().set({ copilotQuestion: "Why did Thames Athletic score?" });
    if (short) {
      await waitFor(() => S().copilotShownAt > shown, 16000, my);   // hard cap keeps the cut under 2:00
      await sleep(4500);  // let the answer be read on screen; the voice keeps going
    } else {
      await waitFor(() => S().copilotAnsweredAt > t, 60000, my);
    }
    if (!short) {
      t = S().copilotAnsweredAt;
      S().set({ demo: { ...S().demo!, sub: "“Explain this like I'm a beginner” → reuses verified text, zero tokens" } });
      S().set({ copilotQuestion: "Explain this like I'm a beginner" });
      await waitFor(() => S().copilotAnsweredAt > t, 40000, my);
    }
    S().set({ voiceOpen: false });

    // 8 — what-if lab
    caption(short ? 8 : 9, TOTAL, "What-if lab: move a defender, and the AI recomputes space and danger.", "Pitch-control model · passing lanes · grounded explanation");
    await enterWhatIf();
    await waitFor(() => !!S().whatIf.result, 20000, my);
    const res = S().whatIf.result;
    if (res) {
      const att = res.attacking_team;
      const home = S().homeId;
      const defs = S().whatIf.base.filter((p) => p.team_id !== att);
      const deep = [...defs].sort((a, b) => (att === home ? b.x - a.x : a.x - b.x))[1];
      if (deep) {
        movePlayer(deep.player_id, deep.x + (att === home ? -14 : 14), deep.y);  // push the defender up — leaves space behind
        runWhatIf(0);
        await waitFor(() => !!S().whatIf.result?.explanation, short ? 12000 : 30000, my);
      }
    }
    await hold(9000);
    exitWhatIf();

    // 9 — the AI sees the counter-attack coming
    caption(short ? 9 : 10, TOTAL, "Late on, the AI flags Thames as exposed on the counter. Then it happens.", "Transition vulnerability → counter-attack goal");
    await jumpTo("78'", short);
    await waitFor(() => clockMin() >= 84, short ? 25000 : 90000, my);
    prefetch(`recap:${S().matchId}:en`, () => fetchRecap(S().matchId, "en"));  // Studio and Coach open later with results ready
    prefetch(`desk:${S().matchId}`, () => api.desk(S().matchId));
    prefetch(`story:${S().matchId}`, () => api.story(S().matchId));
    await hold(3000);
    S().set({ replay: await api.replay(S().matchId, "pause") });
    if (!short) {
      S().set({ screen: "agents" });
      caption(11, TOTAL, "Thirty agents. Every run traced. Most events cost nothing.", "Live latency · tokens · cache hits · LangGraph path");
      await sleep(8000);
    }

    // 10 — story
    S().set({ screen: "story" });
    const before = S().storyReadyAt;
    S().set({ storyRequest: Date.now(), demo: { ...S().demo!, caption: "From thousands of events to a verified match story.", sub: "5 moments · how it was won · player of the match" } });
    speak("From thousands of events to a verified match story.", "tactical_analyst");
    await waitFor(() => S().storyReadyAt > before, short ? 7000 : 60000, my);
    await hold(9000);
    if (!short) {
      const tour: [string, string, string][] = [
        ["tactics", "Tactics: passing networks, live shape, team metrics and predictions.", "Every number comes from the deterministic tactical engine"],
        ["players", "Player intelligence: influence ranking, touch maps and connections.", "Plus long-term memory for every player"],
        ["history", "History: now versus then, retrieved by agentic RAG.", "Shared patterns, same teams, relevance scores"],
        ["fan", "Personalisation: one verified call, four audiences.", "Beginner · intermediate · advanced · professional"],
      ];
      for (const [i, [screen, text, sub]] of tour.entries()) {
        S().set({ screen: screen as any });
        caption(12 + i, TOTAL, text, sub);
        await sleep(5000);
      }
    }

    // Studio, Microsoft Agent Framework desk, production traces and accessibility.
    // These are real API calls/screens, included in both new recordings.
    const featureStep = short ? 11 : 16;
    S().set({ screen: "studio" });
    const studioBefore = S().studioReadyAt;
    caption(featureStep, TOTAL, "One click turns verified facts into every broadcast format.", "Lower-third · social · push · newsletter · two-host podcast · 14 languages");
    S().set({ studioRequest: Date.now() });
    await waitFor(() => S().studioReadyAt > studioBefore, short ? 12000 : 35000, my);
    await sleep(short ? 4500 : 6500);

    S().set({ screen: "coach" });
    const coachBefore = S().coachReadyAt;
    caption(featureStep + 1, TOTAL, "A Microsoft Agent Framework desk creates the coach report.", "Evidence analyst → coach strategist → verifier → PDF publisher");
    S().set({ coachRequest: Date.now() });
    await waitFor(() => S().coachReadyAt > coachBefore, short ? 12000 : 40000, my);
    await sleep(short ? 4500 : 7500);

    S().set({ screen: "traces" });
    caption(featureStep + 2, TOTAL, "Every agent handoff is observable in production.", "OpenTelemetry waterfall · p50/p95 · errors · Application Insights · no prompt capture");
    await sleep(short ? 3800 : 8000);

    S().set({ screen: "live" });
    window.dispatchEvent(new Event("fios:a11y-demo"));
    caption(featureStep + 3, TOTAL, "Built for every fan, including blind and low-vision supporters.", "Live audio description · high contrast · large text · keyboard control");
    await sleep(short ? 3800 : 8000);
    window.dispatchEvent(new Event("fios:a11y-demo-close"));

    S().set({ screen: "live", demo: { running: false, step: TOTAL, total: TOTAL, caption: "Every match. Every moment. Explained by AI.", sub: "Football Intelligence OS" } });
    speak("Every match. Every moment. Explained by AI.", "tactical_analyst");
    await hold(short ? 5000 : 7000);
    if (my === token) S().set({ demo: null });
  } catch {
    /* stopped */
  }
}
