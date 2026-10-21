import { create } from "zustand";
import type { AgentStatus, FanProfile, Insight, JumpPoint, MatchEvent, Pattern, Player, Position, ReplayStatus, SceneCommand, TeamMeta } from "./types";

export type Screen = "live" | "pipeline" | "studio" | "coach" | "tactics" | "story" | "players" | "teams" | "agents" | "traces" | "history" | "fan";

interface RunInfo { run_id: string; event_id?: string; category?: string; significance?: number; reasons?: string[]; started: number; done?: boolean; duration_ms?: number; tokens?: number; graph_path?: string[]; plan?: any; cache_hit?: boolean }

export interface WhatIfState {
  active: boolean; eventId?: string; clock?: string; base: Position[]; moves: Record<string, [number, number]>;
  result: any | null; loading: boolean; dragging: string | null;
}

interface Toast { id: number; kind: "pattern" | "goal" | "alert" | "info"; title: string; body?: string; color?: string }

interface State {
  matchId: string;
  homeId: string;
  awayId: string;
  match: any;
  jumpPoints: JumpPoint[];
  connected: boolean;
  teams: Record<string, TeamMeta>;
  roster: Record<string, Player>;
  positions: Position[];
  lastEvent: MatchEvent | null;
  recentEvents: MatchEvent[];
  score: Record<string, number>;
  clock: string;
  momentum: number;
  momentumSeries: number[];
  context: any;
  activePatterns: Pattern[];
  insights: Insight[];
  featuredId: string | null;
  scene: { commands: SceneCommand[]; source: string | null; label?: string; ghost?: SceneCommand[] };
  replayFrames: MatchEvent[] | null;
  agents: Record<string, AgentStatus>;
  runs: RunInfo[];
  replay: ReplayStatus | null;
  profile: FanProfile;
  screen: Screen;
  whyId: string | null;
  voiceOpen: boolean;
  autoVoice: boolean;
  heatTeam: string | null;
  touches: Record<string, [number, number][]>;
  toasts: Toast[];
  followLive: boolean;
  whatIf: WhatIfState;
  setWhatIf: (p: Partial<WhatIfState>) => void;
  copilotQuestion: string | null;      // set by Auto Demo; the assistant asks it
  storyRequest: number;                // set by Auto Demo; the Story screen generates
  pipelineRequest: { insightId?: string; at: number; speed: number } | null;  // Auto Demo → Pipeline walkthrough
  pipelineDoneAt: number;
  storyReadyAt: number;
  studioRequest: number;
  studioReadyAt: number;
  coachRequest: number;
  coachReadyAt: number;
  copilotAnsweredAt: number;           // timestamp of the last finished (spoken) answer
  copilotShownAt: number;              // timestamp the last answer appeared on screen
  demo: { running: boolean; step: number; total: number; caption: string; sub?: string } | null;
  set: (p: Partial<State>) => void;
  onEvent: (msg: any) => void;
  onEventBatch: (msgs: any[]) => void;
  onInsight: (ins: Insight) => void;
  onAgent: (s: any) => void;
  onRunStarted: (m: any) => void;
  onRunComplete: (m: any) => void;
  onRouting: (m: any) => void;
  focusInsight: (ins: Insight) => void;
  toast: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

const DEFAULT_PROFILE: FanProfile = {
  user_id: "alex", display_name: "Alex", favorite_team_id: "azc", favorite_player_id: "azc_10",
  knowledge_level: "intermediate", persona: "casual_commentator",
  language: (typeof location !== "undefined" && new URLSearchParams(location.search).get("lang")) || "en", interests: [],
};

let toastSeq = 0;
function initialMatch(): string {
  if (typeof location === "undefined") return "live-demo";
  const q = new URLSearchParams(location.search).get("match");
  if (q) return q === "demo" ? "live-demo" : q;
  return "live-demo";  // synthetic demo match by default (hackathon rule: synthetic, football-realistic data)
}
const SCREENS: Screen[] = ["live", "pipeline", "studio", "coach", "tactics", "story", "players", "teams", "agents", "traces", "history", "fan"];
const initialScreen = (): Screen => {
  const h = typeof location !== "undefined" ? location.hash.slice(1) : "";
  return (SCREENS as string[]).includes(h) ? (h as Screen) : "live";
};

export const useStore = create<State>((set, get) => ({
  matchId: initialMatch(),
  homeId: "azc",
  awayId: "tha",
  match: null,
  jumpPoints: [],
  connected: false,
  teams: {},
  roster: {},
  positions: [],
  lastEvent: null,
  recentEvents: [],
  score: {},
  clock: "00:00",
  momentum: 0,
  momentumSeries: [],
  context: null,
  activePatterns: [],
  insights: [],
  featuredId: null,
  scene: { commands: [], source: null },
  replayFrames: null,
  agents: {},
  runs: [],
  replay: null,
  profile: DEFAULT_PROFILE,
  screen: initialScreen(),
  whyId: null,
  voiceOpen: false,
  autoVoice: false,
  heatTeam: null,
  touches: {},
  toasts: [],
  followLive: true,
  whatIf: { active: false, base: [], moves: {}, result: null, loading: false, dragging: null },
  copilotQuestion: null,
  storyRequest: 0,
  pipelineRequest: null,
  pipelineDoneAt: 0,
  storyReadyAt: 0,
  studioRequest: 0,
  studioReadyAt: 0,
  coachRequest: 0,
  coachReadyAt: 0,
  copilotAnsweredAt: 0,
  copilotShownAt: 0,
  demo: null,
  setWhatIf: (p) => set((s) => ({ whatIf: { ...s.whatIf, ...p } })),
  set: (p) => set(p),

  onEventBatch: (msgs) => {
    if (!msgs.length) return;
    const s = get();
    const touches = { ...s.touches };
    const recent = [...s.recentEvents];
    const mom = [...s.momentumSeries];
    let context = s.context, active = s.activePatterns;
    for (const msg of msgs) {
      const ev: MatchEvent = msg.event;
      if (ev.team && ev.x != null && ["PASS", "CARRY", "SHOT"].includes(ev.type)) {
        touches[ev.team] = [...(touches[ev.team] ?? []).slice(-700), [ev.x, ev.y!]];
      }
      recent.push(ev);
      mom.push(msg.momentum);
      if (msg.context) { context = msg.context; active = msg.context.active_patterns ?? active; }
      for (const pc of msg.pattern_changes ?? []) {
        if (pc.kind === "start") get().toast({ kind: "pattern", title: pc.type.replaceAll("_", " "), body: pc.summary, color: s.teams[pc.team_id]?.colors.primary });
      }
      if (ev.type === "GOAL") {
        const team = s.teams[ev.team ?? ""];
        get().toast({ kind: "goal", title: `GOAL — ${team?.name ?? ""}`, body: `${ev.player} · ${ev.clock}`, color: team?.colors.primary });
      }
    }
    const last = msgs[msgs.length - 1];
    const withPos = [...msgs].reverse().find((m) => m.event.positions?.length);
    set({
      lastEvent: last.event, positions: withPos ? withPos.event.positions : s.positions,
      recentEvents: recent.slice(-40), score: last.score, clock: last.event.clock, momentum: last.momentum,
      momentumSeries: mom.slice(-300), touches, context, activePatterns: active,
    });
  },

  onEvent: (msg) => {
    const ev: MatchEvent = msg.event;
    const s = get();
    const touches = { ...s.touches };
    if (ev.team && ev.x != null && ["PASS", "CARRY", "SHOT"].includes(ev.type)) {
      touches[ev.team] = [...(touches[ev.team] ?? []).slice(-700), [ev.x, ev.y!]];
    }
    const patch: Partial<State> = {
      lastEvent: ev,
      positions: ev.positions?.length ? ev.positions : s.positions,
      recentEvents: [...s.recentEvents.slice(-39), ev],
      score: msg.score,
      clock: ev.clock,
      momentum: msg.momentum,
      momentumSeries: [...s.momentumSeries.slice(-299), msg.momentum],
      touches,
    };
    if (msg.context) {
      patch.context = msg.context;
      patch.activePatterns = msg.context.active_patterns ?? s.activePatterns;
    }
    set(patch);
    for (const pc of msg.pattern_changes ?? []) {
      const team = s.teams[pc.team_id];
      if (pc.kind === "start") {
        get().toast({ kind: "pattern", title: pc.type.replaceAll("_", " "), body: pc.summary, color: team?.colors.primary });
      }
    }
    if (ev.type === "GOAL") {
      const team = s.teams[ev.team ?? ""];
      get().toast({ kind: "goal", title: `GOAL — ${team?.name ?? ""}`, body: `${ev.player} · ${ev.clock}`, color: team?.colors.primary });
    }
  },

  onInsight: (ins) => {
    const s = get();
    if (s.insights.some((i) => i.insight_id === ins.insight_id)) return;
    const insights = [...s.insights, ins].sort((a, b) => a.minute * 60 + a.second - (b.minute * 60 + b.second));
    set({ insights });
    if (ins.category !== "ANSWER" && ins.significance >= 0.6 && s.followLive) get().focusInsight(ins);
  },

  focusInsight: (ins) => {
    set({ featuredId: ins.insight_id, scene: { commands: ins.visualization ?? [], source: ins.insight_id, label: ins.headline } });
  },

  onAgent: (m) => {
    set((s) => ({ agents: { ...s.agents, [m.agent]: { ...m, at: Date.now() } } }));
  },
  onRunStarted: (m) => set((s) => ({ runs: [{ ...m, started: Date.now() }, ...s.runs].slice(0, 30) })),
  onRunComplete: (m) => set((s) => ({ runs: s.runs.map((r) => (r.run_id === m.run_id ? { ...r, ...m, done: true } : r)) })),
  onRouting: (m) => set((s) => ({ runs: s.runs.map((r) => (r.run_id === m.run_id ? { ...r, plan: m.plan } : r)) })),

  toast: (t) => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts.slice(-3), { ...t, id }] }));
    setTimeout(() => get().dismiss(id), 6500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export const levelOf = (p: FanProfile) => p.knowledge_level;

// Dev-only handle for automated browser tests (stripped from production builds).
if (import.meta.env.DEV && typeof window !== "undefined") (window as any).__fios = { useStore };
