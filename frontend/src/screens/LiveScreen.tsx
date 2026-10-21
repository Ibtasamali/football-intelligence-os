import { lazy, Suspense, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FlaskConical, Flame, Play, Radar, X } from "lucide-react";
import WhatIfPanel from "../components/WhatIfPanel";
import { enterWhatIf, exitWhatIf } from "../lib/whatif";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { endReplay } from "../lib/replay";
import InsightCard from "../components/InsightCard";
import Timeline from "../components/Timeline";
import AgentTicker from "../components/AgentTicker";
import { Panel } from "../components/ui";

const Scene = lazy(() => import("../three/Scene"));

export default function LiveScreen() {
  const insights = useStore((s) => s.insights);
  const scene = useStore((s) => s.scene);
  const frames = useStore((s) => s.replayFrames);
  const teams = useStore((s) => s.teams);
  const heatTeam = useStore((s) => s.heatTeam);
  const set = useStore((s) => s.set);
  const lastEvent = useStore((s) => s.lastEvent);
  const patterns = useStore((s) => s.activePatterns);
  const [filter, setFilter] = useState<"key" | "all">("key");
  const replay = useStore((s) => s.replay);
  const matchId = useStore((s) => s.matchId);
  const match = useStore((s) => s.match);
  const [starting, setStarting] = useState(false);
  const start = async () => {
    setStarting(true);
    try { set({ replay: await api.replay(matchId, "start") }); } finally { setStarting(false); }
  };
  const whatIfActive = useStore((s) => s.whatIf.active);
  const demoRunning = useStore((s) => !!s.demo?.running);
  const notStarted = replay && !replay.running && replay.index === 0;
  const paused = replay && !replay.running && replay.index > 0 && !replay.finished;
  const feed = useMemo(() => {
    const list = insights.filter((i) => i.category !== "ANSWER" && (filter === "all" || i.significance >= 0.5));
    return [...list].reverse().slice(0, 40);
  }, [insights, filter]);

  return (
    <div className="grid h-full grid-cols-[minmax(0,1fr)_minmax(300px,380px)] gap-3 p-3">
      <div className="flex min-h-0 flex-col gap-3">
        <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-2xl border border-white/[0.07]">
          <Suspense fallback={<div className="grid h-full place-items-center text-slate-500">Building stadium…</div>}><Scene /></Suspense>
          <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-ink-950/80 to-transparent" />
          <div className="absolute left-4 top-3 flex max-w-[60%] flex-col gap-2">
            <AnimatePresence mode="wait">
              {scene.label && (
                <motion.div key={scene.source} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                            className="glass-strong px-3 py-2">
                  <div className="label text-cyan-300">{frames ? "3D replay of AI insight" : "AI focus"}</div>
                  <div className="font-display text-[15px] font-semibold text-white">{scene.label}</div>
                </motion.div>
              )}
            </AnimatePresence>
            {patterns.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {patterns.map((p) => (
                  <span key={p.type + p.team_id} className="chip pointer-events-auto bg-black/50 text-[11px]" title={p.summary}
                        style={{ color: teams[p.team_id]?.colors.primary }}>
                    <Radar size={11} /> {p.type.replaceAll("_", " ").toLowerCase()} · {teams[p.team_id]?.short} · since {p.started_minute}'
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="absolute right-3 top-3 flex gap-1.5">
            {frames && <button className="btn bg-black/50" onClick={endReplay}><X size={13} /> Back to live</button>}
            {!notStarted && (
              <button className={`btn bg-black/50 ${whatIfActive ? "border-fuchsia-300/60 text-fuchsia-200" : "text-fuchsia-200"}`}
                      onClick={() => (whatIfActive ? exitWhatIf() : enterWhatIf())}>
                <FlaskConical size={13} /> {whatIfActive ? "Exit what-if" : "What-if"}
              </button>
            )}
            {Object.entries(teams).map(([id, t]) => (
              <button key={id} className={`btn bg-black/50 ${heatTeam === id ? "border-white/40" : ""}`} style={{ color: t.colors.primary }}
                      onClick={() => set({ heatTeam: heatTeam === id ? null : id })}><Flame size={13} /> {t.short} heatmap</button>
            ))}
          </div>
          {notStarted && !frames && (
            <div className="absolute inset-0 z-10 grid place-items-center bg-ink-950/55 backdrop-blur-[2px]">
              <div className="text-center">
                <div className="label mb-2 text-cyan-300">{match?.source === "statsbomb" ? "Real match · StatsBomb data" : "Demo match"}</div>
                <div className="mb-6 font-display text-3xl font-bold text-white">{match?.competition ?? "Ready"}</div>
                <button onClick={start} disabled={starting}
                        className="mx-auto flex items-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-400 to-sky-500 px-10 py-5 font-display text-2xl font-bold text-ink-950 shadow-[0_0_60px_rgba(34,211,238,.6)] transition hover:scale-105">
                  <Play size={30} fill="currentColor" /> {starting ? "Starting…" : "START MATCH"}
                </button>
                <div className="mx-auto mt-6 max-w-md space-y-1 text-left text-[13px] text-slate-300">
                  <div>① Players move and the AI watches every event.</div>
                  <div>② When something important happens, AI insight cards appear on the right →</div>
                  <div>③ Click <b>Why?</b> on a card for the evidence, or the glowing button (bottom-right) to ask a question.</div>
                </div>
              </div>
            </div>
          )}
          <WhatIfPanel />
          {paused && !frames && !whatIfActive && !demoRunning && (
            <button onClick={start} className="absolute left-1/2 top-1/2 z-10 flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 rounded-xl bg-ink-950/80 px-6 py-3 font-display text-lg font-semibold text-white ring-1 ring-cyan-300/50 hover:bg-ink-900">
              <Play size={20} fill="currentColor" /> Paused at {replay?.clock} · Resume
            </button>
          )}
          {lastEvent && (
            <div className="absolute bottom-3 left-4 font-mono text-[11px] text-slate-300/80">
              {lastEvent.clock} · {lastEvent.type} · {lastEvent.player ?? ""} {lastEvent.outcome ? `· ${lastEvent.outcome}` : ""}
            </div>
          )}
        </div>
        <AgentTicker />
        <Timeline />
      </div>
      <Panel title="AI commentary & insights" className="min-h-0"
             right={<div className="flex gap-1">{(["key", "all"] as const).map((f) => (
               <button key={f} onClick={() => setFilter(f)} className={`chip ${filter === f ? "text-cyan-200" : "text-slate-500"}`}>{f === "key" ? "Key moments" : "All"}</button>))}</div>}>
        <div className="h-full space-y-2.5 overflow-y-auto p-3">
          {feed.length === 0 && (
            <div className="grid h-full place-items-center text-center text-sm text-slate-500">
              <div>Press <span className="text-cyan-300">Kick off</span>.<br />Routine events stay on the zero-token fast path;<br />the agents wake up when something matters.</div>
            </div>
          )}
          <AnimatePresence initial={false}>{feed.map((i, idx) => <InsightCard key={i.insight_id} ins={i} translate={idx < 5} />)}</AnimatePresence>
        </div>
      </Panel>
    </div>
  );
}
