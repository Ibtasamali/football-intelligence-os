import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Cloud, LockKeyhole, Pause, Play, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { Panel, Stat } from "../components/ui";

const KINDS: Record<string, { label: string; color: string; bar: string }> = {
  langgraph: { label: "LangGraph", color: "text-cyan-200", bar: "from-cyan-500/80 to-sky-400/80" },
  agent: { label: "Agent", color: "text-violet-200", bar: "from-violet-500/80 to-fuchsia-400/70" },
  llm: { label: "Azure OpenAI", color: "text-amber-200", bar: "from-amber-500/80 to-yellow-300/80" },
  agent_framework: { label: "Agent Framework", color: "text-emerald-200", bar: "from-emerald-500/80 to-teal-300/80" },
  http: { label: "API", color: "text-slate-200", bar: "from-slate-500/80 to-slate-400/70" },
  service: { label: "Service", color: "text-sky-200", bar: "from-sky-600/80 to-sky-400/70" },
};
const FILTERS = [["all", "All"], ["langgraph", "Live analysis"], ["agent_framework", "Agent Framework"], ["http", "API calls"]] as const;

function ago(ms: number) {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
}

function detail(s: any) {
  const a = s.attributes ?? {};
  const bits = [a["agent.name"], a["model.name"] ?? a["gen_ai.request.model"], a["model.tier"] && `tier ${a["model.tier"]}`,
    a["gen_ai.usage.input_tokens"] != null && `${a["gen_ai.usage.input_tokens"]}→${a["gen_ai.usage.output_tokens"]} tokens`,
    a["category"], a["workflow.name"], a["http.route"]];
  return bits.filter(Boolean).join(" · ");
}

export default function TracingScreen() {
  const matchId = useStore((s) => s.matchId);
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [live, setLive] = useState(true);
  const [picked, setPicked] = useState<any>(null);
  const load = () => api.traces(matchId).then(setData).catch(() => {});
  useEffect(() => { load(); if (!live) return; const t = setInterval(load, 2500); return () => clearInterval(t); }, [matchId, live]);
  const traces = useMemo(() => (data?.traces ?? []).filter((t: any) => filter === "all" || t.kind === filter), [data, filter]);
  // default to the latest trace that shows real agent work, not a one-span API call
  const current = selected || (traces.find((t: any) => t.spans >= 5) ?? traces[0])?.trace_id;
  const rows = useMemo(() => {
    const spans = (data?.spans ?? []).filter((s: any) => s.trace_id === current);
    const ids = new Set(spans.map((s: any) => s.span_id));
    const kids: Record<string, any[]> = {};
    for (const s of spans) (kids[s.parent_span_id && ids.has(s.parent_span_id) ? s.parent_span_id : "root"] ??= []).push(s);
    const out: any[] = [];
    const walk = (key: string, depth: number) => (kids[key] ?? []).sort((a, b) => a.start_ms - b.start_ms).forEach((s) => { out.push({ ...s, depth }); walk(s.span_id, depth + 1); });
    walk("root", 0);
    return out;
  }, [data, current]);
  const start = rows.length ? Math.min(...rows.map((s) => s.start_ms)) : 0;
  const range = Math.max(1, rows.length ? Math.max(...rows.map((s) => s.start_ms + s.duration_ms)) - start : 1);
  const tokens = (data?.traces ?? []).reduce((n: number, t: any) => n + (t.tokens || 0), 0);
  const llm = (data?.traces ?? []).reduce((n: number, t: any) => n + (t.llm_calls || 0), 0);
  return <div className="grid h-full grid-rows-[auto_1fr] gap-3 overflow-hidden p-4">
    <div className="grid grid-cols-3 gap-2 lg:grid-cols-6">
      <Stat label="Traces" value={data?.trace_count ?? 0} sub="OpenTelemetry" />
      <Stat label="Spans" value={data?.span_count ?? 0} accent="#22D3EE" sub="graph nodes · agents · LLM" />
      <Stat label="LLM calls" value={llm} accent="#FACC15" sub={`${tokens.toLocaleString()} tokens`} />
      <Stat label="Errors" value={data?.errors ?? 0} accent={(data?.errors ?? 0) ? "#F87171" : "#34D399"} />
      <Stat label="p95 span" value={`${data?.p95_ms ?? 0} ms`} sub={`p50 ${data?.p50_ms ?? 0} ms`} />
      <Stat label="Privacy" value="Safe" sub="metadata only, no prompts" accent="#34D399" />
    </div>
    <div className="grid min-h-0 grid-cols-[330px_1fr] gap-3">
      <Panel title="Traces" right={<div className="flex gap-1">
        <button className="btn" onClick={() => setLive(!live)} aria-label={live ? "Pause live updates" : "Resume live updates"}>{live ? <Pause size={12} /> : <Play size={12} />}</button>
        <button className="btn" onClick={load} aria-label="Refresh"><RefreshCw size={12} /></button></div>}>
        <div className="flex flex-wrap gap-1 px-2 pt-2">{FILTERS.map(([k, l]) =>
          <button key={k} onClick={() => setFilter(k)} className={`chip ${filter === k ? "border-cyan-300/50 text-cyan-200" : "text-slate-400"}`}>{l}</button>)}</div>
        <div className="h-[calc(100%-40px)] overflow-y-auto p-2">
          {traces.map((t: any) => {
            const k = KINDS[t.kind] ?? KINDS.service;
            return <button key={t.trace_id} onClick={() => { setSelected(t.trace_id); setPicked(null); }}
              className={`mb-1 w-full rounded-lg p-2.5 text-left ${current === t.trace_id ? "bg-cyan-400/10 ring-1 ring-cyan-300/30" : "bg-white/[0.025] hover:bg-white/[0.05]"}`}>
              <div className="flex items-center gap-2"><span className={`truncate font-mono text-[12px] ${k.color}`}>{t.name}</span>
                {t.errors > 0 && <AlertTriangle size={12} className="shrink-0 text-rose-300" />}</div>
              <div className="mt-1 flex flex-wrap gap-x-2 text-[10px] text-slate-400">
                <span>{k.label}</span><span>{t.spans} spans</span>{t.agents > 0 && <span>{t.agents} agents</span>}
                {t.llm_calls > 0 && <span className="text-amber-200/80">{t.llm_calls} LLM · {t.tokens} tok</span>}
                <span className="ml-auto">{Math.round(t.duration_ms)} ms · {ago(t.start_ms)}</span></div>
            </button>;
          })}
          {!traces.length && <div className="p-5 text-center text-xs text-slate-500">Play the match, ask the Copilot or generate a coach report — every run appears here.</div>}
        </div>
      </Panel>
      <Panel title="Trace waterfall" right={<div className="flex gap-2"><span className="chip text-cyan-200"><Cloud size={12} /> exports to Application Insights</span><span className="chip text-emerald-300"><LockKeyhole size={12} /> no prompts stored</span></div>}>
        <div className="grid h-full min-h-0 grid-rows-[1fr_auto]">
          <div className="overflow-auto p-4">
            <div className="mb-2 grid grid-cols-[300px_1fr_80px] gap-3 text-[10px] uppercase tracking-wider text-slate-500"><span>Operation</span><span>Timeline</span><span className="text-right">Duration</span></div>
            {rows.map((s) => {
              const k = KINDS[s.kind] ?? KINDS.service;
              const left = ((s.start_ms - start) / range) * 100;
              const width = Math.max(0.8, (s.duration_ms / range) * 100);
              return <button key={s.span_id} onClick={() => setPicked(s)} className={`grid w-full grid-cols-[300px_1fr_80px] items-center gap-3 border-t border-white/[0.04] py-1.5 text-left hover:bg-white/[0.03] ${picked?.span_id === s.span_id ? "bg-white/[0.05]" : ""}`}>
                <div style={{ paddingLeft: Math.min(s.depth, 8) * 14 }} className="min-w-0">
                  <div className={`truncate font-mono text-[11.5px] ${k.color}`}>{s.name}</div>
                  <div className="truncate text-[9.5px] text-slate-500">{detail(s) || k.label}</div></div>
                <div className="relative h-5 rounded bg-white/[0.025]"><div className={`absolute top-1 h-3 rounded bg-gradient-to-r ${s.status === "error" ? "from-rose-500 to-rose-400" : k.bar}`} style={{ left: `${left}%`, width: `${width}%` }} /></div>
                <div className={`text-right font-mono text-[10.5px] ${s.status === "error" ? "text-rose-300" : "text-slate-300"}`}>{s.duration_ms < 1 ? s.duration_ms.toFixed(2) : Math.round(s.duration_ms)} ms</div>
              </button>;
            })}
            {!rows.length && <div className="p-8 text-center text-sm text-slate-500">Select a trace.</div>}
          </div>
          {picked && <div className="max-h-40 overflow-y-auto border-t border-white/10 p-3 font-mono text-[10.5px] text-slate-300">
            <div className="mb-1 text-cyan-200">{picked.name} · {picked.status}{picked.error ? ` · ${picked.error}` : ""}</div>
            {Object.entries(picked.attributes ?? {}).map(([k, v]) => <div key={k}><span className="text-slate-500">{k}</span> = {String(v)}</div>)}
          </div>}
        </div>
      </Panel>
    </div>
  </div>;
}
