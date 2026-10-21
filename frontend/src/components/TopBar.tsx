import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Pause, Play, Radio, Clapperboard, Volume2, VolumeX, FastForward, CircleHelp } from "lucide-react";
import { useStore } from "../lib/store";
import { api } from "../lib/api";
import { refreshReplay, switchMatch } from "../lib/live";
import { runDemo, stopDemo } from "../lib/autodemo";
import { stopSpeaking } from "../lib/voice";
import { type Lang, loadLanguages } from "../lib/i18n";
import A11yPanel from "./A11yPanel";

export default function TopBar() {
  const { teams, score, clock, connected, replay, matchId, profile, autoVoice, set, momentum, homeId, awayId, jumpPoints, match, demo } = useStore();
  const [busy, setBusy] = useState(false);
  const [catalog, setCatalog] = useState<any[]>([]);
  const [langs, setLangs] = useState<Lang[]>([]);
  useEffect(() => { loadLanguages().then(setLangs).catch(() => {}); }, []);
  useEffect(() => {
    const id = setInterval(refreshReplay, 1500);
    api.matchCatalog().then((c) => setCatalog(c.matches)).catch(() => {});
    return () => clearInterval(id);
  }, []);
  const h = teams[homeId], a = teams[awayId];
  const currentKey = matchId === "live-demo" ? "demo" : matchId;
  const running = replay?.running;
  const toggle = async () => {
    setBusy(true);
    try {
      set({ replay: await api.replay(matchId, running ? "pause" : "start") });
    } finally {
      setBusy(false);
    }
  };
  const jump = async (i: number) => {
    const j = jumpPoints[i];
    if (!j) return;
    if (j.minute === 0 && !j.seq) {
      setBusy(true);
      try { await switchMatch(currentKey); } finally { setBusy(false); }
      return;
    }
    set({ replay: await api.jump(matchId, j.minute, j.seq) });
  };
  const pick = async (key: string) => {
    setBusy(true);
    try { await switchMatch(key); } finally { setBusy(false); }
  };
  return (
    <header className="relative z-20 flex h-16 min-w-0 items-center gap-3 overflow-hidden border-b border-white/[0.06] bg-ink-950/80 px-3 backdrop-blur-xl">
      <div className="flex shrink-0 items-center gap-3">
        <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-sky-600 shadow-glow">
          <div className="h-3.5 w-3.5 rounded-full border-[3px] border-ink-950" />
        </div>
        <div className="hidden leading-tight 2xl:block">
          <div className="whitespace-nowrap font-display text-[15px] font-bold tracking-tight text-white">FOOTBALL INTELLIGENCE OS</div>
          <div className="hidden text-[10px] uppercase tracking-[0.2em] text-cyan-300/80 2xl:block">Every match. Every moment. Explained by AI.</div>
        </div>
      </div>

      <div className="mx-auto flex shrink-0 items-center gap-2">
        <TeamPill name={h?.name} short={h?.short} color={h?.colors.primary} />
        <div className="glass-strong flex items-center gap-3 px-4 py-1.5">
          <motion.span key={`h${score[homeId]}`} initial={{ scale: 1.6, color: "#fde047" }} animate={{ scale: 1, color: "#fff" }}
                       className="font-display text-2xl font-bold tabular-nums">{score[homeId] ?? 0}</motion.span>
          <div className="flex flex-col items-center">
            <span className="font-mono text-sm tabular-nums text-cyan-200">{clock}</span>
            <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-red-400">
              <span className={`h-1.5 w-1.5 rounded-full ${running ? "animate-pulse bg-red-500" : "bg-slate-600"}`} />
              {replay?.finished ? "FT" : running ? "Live" : "Paused"}
            </span>
          </div>
          <motion.span key={`a${score[awayId]}`} initial={{ scale: 1.6, color: "#fde047" }} animate={{ scale: 1, color: "#fff" }}
                       className="font-display text-2xl font-bold tabular-nums">{score[awayId] ?? 0}</motion.span>
        </div>
        <TeamPill name={a?.name} short={a?.short} color={a?.colors.primary} right />
        <div className="ml-2 hidden w-28 2xl:block" title="Momentum (threat-weighted, decaying)">
          <div className="label mb-1 text-center">Momentum</div>
          <div className="relative h-1.5 rounded-full bg-white/10">
            <motion.div className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-white"
                        animate={{ left: `calc(${50 - momentum * 50}% - 6px)`, background: momentum > 0 ? h?.colors.primary : a?.colors.primary }} />
          </div>
        </div>
      </div>

      <div className="flex min-w-0 items-center gap-1.5">
        <button onClick={() => (demo?.running ? stopDemo() : runDemo())}
                className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold transition ${demo?.running ? "bg-rose-500 text-white" : "bg-gradient-to-r from-fuchsia-400 to-violet-500 text-white shadow-[0_0_24px_rgba(217,70,239,.45)] hover:brightness-110"}`}>
          {demo?.running ? "■ Stop demo" : "✦ Auto Demo"}
        </button>
        {!demo?.running && (
          <button onClick={() => runDemo(true)} title="Under-2-minute cut for the submission video"
                  className="hidden shrink-0 rounded-lg border border-fuchsia-300/40 px-2.5 py-1.5 text-xs font-semibold text-fuchsia-200 hover:bg-fuchsia-400/10 xl:inline-flex">
            🎬 2-min video
          </button>
        )}
        <button data-tour="kickoff" className="btn-primary shrink-0" onClick={toggle} disabled={busy}>
          {running ? <Pause size={14} /> : <Play size={14} />} {running ? "Pause" : replay?.index ? "Resume" : "Kick off"}
        </button>
        <select className="btn max-w-[190px] bg-ink-900" value={currentKey} disabled={busy} onChange={(e) => pick(e.target.value)}
                title="Choose a match">
          {catalog.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
        <select className="btn bg-ink-900" value="" onChange={(e) => e.target.value !== "" && jump(Number(e.target.value))}>
          <option value="">Jump to…</option>
          {jumpPoints.map((j, i) => <option key={i} value={i}>{j.label}</option>)}
        </select>
        <button className={`btn hidden xl:inline-flex ${replay?.director ? "border-cyan-300/50 text-cyan-200" : ""}`}
                title="Director mode slows down around tactical moments"
                onClick={async () => set({ replay: await api.speed(matchId, replay?.speed ?? 20, !replay?.director) })}>
          <Clapperboard size={14} /> Director
        </button>
        <button className="btn hidden xl:inline-flex" title="Speed ×2" onClick={async () => set({ replay: await api.speed(matchId, Math.min(240, (replay?.speed ?? 20) * 2), false) })}>
          <FastForward size={14} /> {Math.round(replay?.speed ?? 0)}×
        </button>
        <button className={`btn ${autoVoice ? "border-cyan-300/50 text-cyan-200" : ""}`} title="Auto voice commentary"
                onClick={() => { if (autoVoice) stopSpeaking(); set({ autoVoice: !autoVoice }); }}>
          {autoVoice ? <Volume2 size={14} /> : <VolumeX size={14} />}
        </button>
        {match?.source === "statsbomb" && <span className="chip hidden whitespace-nowrap 2xl:inline-flex text-[10px] text-amber-200" title={match.notes?.attribution}>Real data · StatsBomb</span>}
        <A11yPanel />
        <button className="btn" title="Replay the 60-second judge tour" onClick={() => window.dispatchEvent(new Event("fios:tour"))}>
          <CircleHelp size={14} />
        </button>
        <select className="btn bg-ink-900" title="Commentary language" value={profile.language || "en"}
                onChange={(e) => { stopSpeaking(); set({ profile: { ...profile, language: e.target.value } }); }}>
          {langs.map((l) => <option key={l.code} value={l.code}>🌐 {l.native}</option>)}
        </select>
        <span className={`chip hidden 2xl:inline-flex ${connected ? "text-emerald-300" : "text-red-300"}`}><Radio size={12} /> {connected ? "Realtime" : "Offline"}</span>
        <div className="chip hidden whitespace-nowrap xl:inline-flex">{profile.display_name} · {profile.knowledge_level}</div>
      </div>
    </header>
  );
}

function TeamPill({ name, short, color, right }: { name?: string; short?: string; color?: string; right?: boolean }) {
  return (
    <div className={`flex items-center gap-2 ${right ? "flex-row-reverse" : ""}`}>
      <div className="grid h-8 w-8 place-items-center rounded-lg font-display text-[11px] font-bold text-white" style={{ background: color, boxShadow: `0 0 24px ${color}66` }}>
        {short}
      </div>
      <span className="hidden font-display text-sm font-semibold text-white 2xl:inline">{name}</span>
    </div>
  );
}
