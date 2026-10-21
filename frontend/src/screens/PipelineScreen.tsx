import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, ChevronLeft, ChevronRight, CircleDashed, Loader2, Pause, Play, Workflow } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { speak } from "../lib/voice";
import { Badge } from "../components/ui";

const FAMILY: Record<string, { color: string; label: string }> = {
  perception: { color: "#22D3EE", label: "Perception" }, tactical: { color: "#FACC15", label: "Tactical" },
  entity: { color: "#A78BFA", label: "Entity" }, knowledge: { color: "#34D399", label: "Knowledge" },
  reasoning: { color: "#F97316", label: "Reasoning" }, experience: { color: "#F472B6", label: "Experience" },
};

export default function PipelineScreen() {
  const { matchId, insights } = useStore();
  const request = useStore((s) => s.pipelineRequest);
  const candidates = insights.filter((i) => i.category !== "ANSWER" && i.significance >= 0.6);
  const [sel, setSel] = useState<string>("");
  const [trace, setTrace] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [shown, setShown] = useState(0);       // agents revealed in the current step
  const [playing, setPlaying] = useState(false);
  const speedRef = useRef(1);
  const narrateRef = useRef(false);

  const load = async (insightId?: string) => {
    setLoading(true);
    setTrace(null);
    try {
      const t = await api.trace(matchId, insightId || undefined);
      setTrace(t);
      setStep(0);
      setShown(0);
      return t;
    } finally {
      setLoading(false);
    }
  };

  // Auto Demo hook
  useEffect(() => {
    if (!request) return;
    speedRef.current = request.speed;
    narrateRef.current = true;
    if (request.insightId) setSel(request.insightId);
    load(request.insightId).then(() => setPlaying(true));
  }, [request?.at]);

  // autoplay: reveal agents one by one, then move to the next step
  useEffect(() => {
    if (!playing || !trace) return;
    const s = trace.steps[step];
    if (!s) return;
    const agentsN = s.agents.length;
    if (shown === 0 && narrateRef.current && s.agents.length) speak(`${s.title}. ${s.description}`, "tactical_analyst");
    const delay = (shown < agentsN ? (shown === 0 ? 2200 : 1100) : 1800) / speedRef.current;
    const id = setTimeout(() => {
      if (shown < agentsN) setShown(shown + 1);
      else if (step < trace.steps.length - 1) { setStep(step + 1); setShown(0); }
      else { setPlaying(false); narrateRef.current = false; useStore.getState().set({ pipelineDoneAt: Date.now() }); }
    }, delay);
    return () => clearTimeout(id);
  }, [playing, trace, step, shown]);

  const s = trace?.steps?.[step];
  const visibleAgents = s ? (playing ? s.agents.slice(0, shown) : s.agents) : [];

  return (
    <div className="grid h-full grid-cols-[240px_minmax(0,1fr)_260px] gap-3 overflow-hidden p-3">
      {/* LangGraph steps */}
      <div className="glass flex min-h-0 flex-col">
        <div className="border-b border-white/[0.06] px-4 py-2.5"><span className="label">LangGraph path</span></div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
          {!trace && <div className="p-2 text-[12px] text-slate-500">Pick a moment and press Walk through.</div>}
          {trace?.steps.map((x: any, i: number) => (
            <button key={i} onClick={() => { setPlaying(false); setStep(i); setShown(x.agents.length); }}
                    className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[12.5px] transition ${
                      i === step ? "bg-cyan-400/15 text-white ring-1 ring-cyan-300/40" : i < step ? "text-slate-300" : "text-slate-500"}`}>
              {i < step ? <CheckCircle2 size={14} className="shrink-0 text-emerald-300" /> : i === step ? <Loader2 size={14} className={`shrink-0 text-cyan-300 ${playing ? "animate-spin" : ""}`} /> : <CircleDashed size={14} className="shrink-0" />}
              <span className="flex-1">{x.title}</span>
              {x.agents.length > 0 && <span className="font-mono text-[10px] text-slate-500">{x.agents.length}</span>}
            </button>
          ))}
        </div>
      </div>

      {/* current step */}
      <div className="flex min-h-0 flex-col gap-3">
        <div className="glass flex flex-wrap items-center gap-3 px-4 py-3">
          <Workflow size={18} className="text-cyan-300" />
          <div className="min-w-0 flex-1">
            <div className="label text-cyan-300">Inside the agents · one moment, step by step</div>
            {trace ? (
              <div className="truncate font-display text-[15px] font-semibold text-white">
                {trace.event.clock} · {trace.event.type} · {trace.event.player} ({trace.event.team})
                {trace.insight && <span className="ml-2 text-slate-400">→ “{trace.insight.headline}”</span>}
              </div>
            ) : <div className="text-[13px] text-slate-400">See exactly which agents run, what each one finds, and how they hand off.</div>}
          </div>
          <select className="btn max-w-[260px] bg-ink-900" value={sel} onChange={(e) => setSel(e.target.value)}>
            <option value="">Latest goal</option>
            {candidates.slice().reverse().map((i) => <option key={i.insight_id} value={i.insight_id}>{i.minute}' {i.headline.slice(0, 40)}</option>)}
          </select>
          <button className="btn-primary" disabled={loading} onClick={async () => { speedRef.current = 1; await load(sel); setPlaying(true); }}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} Walk through
          </button>
          {trace && (
            <div className="flex gap-1">
              <button className="btn" onClick={() => { setPlaying(false); setStep(Math.max(0, step - 1)); setShown(99); }}><ChevronLeft size={14} /></button>
              <button className="btn" onClick={() => setPlaying(!playing)}>{playing ? <Pause size={14} /> : <Play size={14} />}</button>
              <button className="btn" onClick={() => { setPlaying(false); setStep(Math.min(trace.steps.length - 1, step + 1)); setShown(99); }}><ChevronRight size={14} /></button>
            </div>
          )}
        </div>

        <div className="glass min-h-0 flex-1 overflow-y-auto p-5">
          {loading && <div className="grid h-full place-items-center text-slate-400"><Loader2 className="animate-spin" /> Running the moment through the graph…</div>}
          {s && (
            <AnimatePresence mode="wait">
              <motion.div key={step} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-400/15 font-mono text-sm font-bold text-cyan-200">{step + 1}</span>
                  <div>
                    <div className="font-display text-xl font-bold text-white">{s.title}</div>
                    <div className="text-[13px] text-slate-400">{s.description}</div>
                  </div>
                  <span className="ml-auto font-mono text-[11px] text-slate-500">step {step + 1} / {trace.steps.length}</span>
                </div>
                {s.decision?.length > 0 && (
                  <div className="mt-4 space-y-1 rounded-xl border border-cyan-300/20 bg-cyan-400/[0.05] p-3">
                    <div className="label text-cyan-300">Decision</div>
                    {s.decision.map((d: string, i: number) => <div key={i} className="text-[13px] text-slate-200">→ {d}</div>)}
                  </div>
                )}
                <div className="mt-4 grid gap-2.5 xl:grid-cols-2">
                  <AnimatePresence>
                    {visibleAgents.map((a: any) => {
                      const f = FAMILY[a.family] ?? { color: "#94A3B8", label: a.family };
                      return (
                        <motion.div key={a.agent} initial={{ opacity: 0, scale: 0.96, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }}
                          className="rounded-xl border bg-white/[0.025] p-3.5" style={{ borderColor: `${f.color}55`, boxShadow: `0 0 24px -12px ${f.color}` }}>
                          <div className="flex items-center gap-2">
                            <span className="h-2.5 w-2.5 rounded-full" style={{ background: f.color }} />
                            <span className="font-mono text-[13px] font-semibold text-white">{a.agent}</span>
                            <span className="chip text-[10px]" style={{ color: f.color }}>{f.label}</span>
                            {a.uses_llm && <span className="chip text-[10px] text-amber-200">LLM</span>}
                            <span className="ml-auto font-mono text-[10.5px] text-slate-500">{a.latency_ms}ms · {a.tokens}t</span>
                          </div>
                          <div className="mt-1 text-[11.5px] text-slate-500">{a.role}</div>
                          <div className="mt-2 space-y-1">
                            {a.findings.map((line: string, i: number) => <div key={i} className="text-[12.5px] leading-snug text-slate-200">{line}</div>)}
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
                {s.agents.length === 0 && !s.decision?.length && <div className="mt-4 text-[13px] text-slate-500">Control step — no specialist agents run here.</div>}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </div>

      {/* all 30 agents */}
      <div className="glass flex min-h-0 flex-col">
        <div className="border-b border-white/[0.06] px-4 py-2.5">
          <span className="label">All 30 agents</span>
          {trace && <div className="mt-0.5 text-[11px] text-slate-400"><span className="text-emerald-300">{trace.agents_ran.length} ran</span> · {30 - trace.agents_ran.length} skipped by the router (not needed for this moment)</div>}
        </div>
        <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
          {(trace?.agents_all ?? []).map((a: any) => {
            const f = FAMILY[a.family] ?? { color: "#94A3B8", label: a.family };
            const active = s?.agents.some((x: any) => x.agent === a.agent);
            return (
              <div key={a.agent} title={a.role}
                   className={`flex items-center gap-2 rounded-md px-2 py-1 font-mono text-[11px] transition ${active ? "bg-white/10 text-white" : a.ran ? "text-slate-300" : "text-slate-600 line-through"}`}>
                <span className="h-2 w-2 rounded-full" style={{ background: a.ran ? f.color : "#334155" }} />{a.agent}
              </div>
            );
          })}
          {!trace && <div className="p-2 text-[12px] text-slate-500">Agents light up as they run.</div>}
        </div>
        {trace && <div className="border-t border-white/[0.06] px-4 py-2 text-[11px] text-slate-500">Whole graph: {trace.duration_ms} ms · <Badge category={trace.insight?.category ?? "ROUTINE"} /></div>}
      </div>
    </div>
  );
}
