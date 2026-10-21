import { api } from "./api";
import { useStore } from "./store";
import { speak } from "./voice";
import { langMeta, translateInsight } from "./i18n";
import { announce, describeEvent, useA11y } from "./a11y";

let socket: WebSocket | null = null;
let retry: number | undefined;
let pending: any[] = [];
let flushTimer: number | undefined;
const flush = () => {
  flushTimer = undefined;
  const batch = pending;
  pending = [];
  useStore.getState().onEventBatch(batch);
};

export async function bootstrap(matchId: string) {
  const st = useStore.getState();
  let m: any;
  try {
    m = await api.match(matchId);
  } catch {
    try {
      const real = matchId !== "live-demo";
      await api.createMatch(matchId, real ? "statsbomb" : "synthetic", real ? matchId : undefined);
    } catch {
      await api.createMatch(matchId, "synthetic");  // real data disabled → synthetic match with this id (e.g. a recording)
    }
    m = await api.match(matchId);
  }
  const roster = Object.fromEntries((m.roster as any[]).map((p) => [p.player_id, p]));
  st.set({
    matchId, teams: m.teams, roster, replay: m.replay, score: m.snapshot.score, homeId: m.home_id, awayId: m.away_id,
    match: m.match, jumpPoints: m.jump_points ?? [], touches: { [m.home_id]: [], [m.away_id]: [] },
    insights: [], featuredId: null, scene: { commands: [], source: null }, momentumSeries: [], recentEvents: [], runs: [], agents: {},
    positions: m.last_event?.positions ?? [], clock: m.last_event?.clock ?? "00:00",
    context: m.context, activePatterns: m.context?.active_patterns ?? [],
  });
  const ins = await api.insights(matchId);
  ins.insights.forEach((i: any) => st.onInsight(i));
  connect(matchId);
}

export function connect(matchId: string) {
  if (socket) {
    // intentional close: detach handlers so the old socket can't trigger a reconnect loop
    socket.onclose = null;
    socket.onmessage = null;
    socket.close();
  }
  clearTimeout(retry);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/matches/${matchId}`);
  socket = ws;
  const st = useStore.getState;
  ws.onopen = () => st().set({ connected: true });
  ws.onclose = () => {
    if (socket !== ws) return;           // a newer connection already replaced this one
    st().set({ connected: false });
    clearTimeout(retry);
    retry = window.setTimeout(() => { if (socket === ws) connect(useStore.getState().matchId); }, 1500);
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    switch (msg.type) {
      case "hello":
        (msg.insights ?? []).forEach((i: any) => st().onInsight(i));
        break;
      case "event":
        if (useA11y.getState().enabled) {
          const d = describeEvent(msg.event, (id) => useStore.getState().teams[id]?.name ?? id);
          if (d) announce(d, { urgent: msg.event.type === "GOAL" });
          for (const pc of msg.pattern_changes ?? []) if (pc.kind === "start") announce(`Tactical change: ${pc.summary}`);
        }
        pending.push(msg);  // batched: the screen updates ~8×/s instead of once per event
        if (flushTimer === undefined) flushTimer = window.setTimeout(flush, 120);
        break;
      case "insight": {
        st().onInsight(msg.insight);
        if (useA11y.getState().enabled && msg.insight.significance >= 0.6 && msg.insight.category !== "ANSWER")
          announce(msg.insight.explanations?.beginner || msg.insight.commentary);
        const s = st();
        if (s.autoVoice && msg.insight.significance >= 0.7 && msg.insight.category !== "ANSWER") {
          const lang = s.profile.language || "en";
          const script = msg.insight.voice_scripts?.[s.profile.persona] ?? msg.insight.commentary;
          if (lang === "en") {
            if (script) speak(script, s.profile.persona);
          } else {
            translateInsight(msg.insight, lang, s.profile.knowledge_level, s.profile.persona)
              .then((l) => speak(l.voice || l.commentary, s.profile.persona, l.language, langMeta(l.language)?.locale))
              .catch(() => script && speak(script, s.profile.persona));
          }
        }
        break;
      }
      case "agent_status":
        st().onAgent(msg);
        break;
      case "run_started":
        st().onRunStarted(msg);
        break;
      case "run_complete":
        st().onRunComplete(msg);
        break;
      case "routing":
        st().onRouting(msg);
        break;
      case "archive_ready":
        st().toast({ kind: "info", title: "Real historical archive ready", body: `${msg.documents} earlier matches analysed for RAG comparisons.` });
        break;
      case "replay_finished":
        st().toast({ kind: "info", title: "Full time", body: "Open Match Story for the AI summary." });
        break;
    }
  };
  const ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 20000);
  ws.addEventListener("close", () => clearInterval(ping));
}

export async function refreshReplay() {
  const s = useStore.getState();
  try {
    const r = await fetch(`/api/matches/${s.matchId}/replay`).then((x) => x.json());
    s.set({ replay: r });
  } catch {
    /* ignore */
  }
}

/** Switch to another match (synthetic demo or a real StatsBomb match) and reconnect. */
export async function switchMatch(key: string, source?: "synthetic" | "statsbomb") {
  const id = key === "demo" ? "live-demo" : key;
  const st = useStore.getState();
  const src = source ?? (key === "demo" ? "synthetic" : "statsbomb");
  await api.createMatch(id, src, src === "statsbomb" ? key : undefined);
  try { localStorage.setItem("fios.match", id); } catch { /* ignore */ }
  st.set({ matchId: id, replayFrames: null });
  await bootstrap(id);
}
