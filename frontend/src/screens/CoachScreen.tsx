import { useEffect, useState } from "react";
import { BadgeCheck, Download, FileText, Loader2, Network, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { take } from "../lib/prefetch";
import { Panel } from "../components/ui";

let handled = 0;  // each auto-demo request runs once (StrictMode re-runs effects; remounts keep old requests)

export default function CoachScreen() {
  const matchId = useStore((s) => s.matchId);
  const started = useStore((s) => (s.replay?.index ?? 0) > 0);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const coachRequest = useStore((s) => s.coachRequest);
  const setStore = useStore((s) => s.set);
  const generate = async () => {
    setBusy(true); setError("");
    try { setResult(await take(`desk:${matchId}`, () => api.desk(matchId))); setStore({ coachReadyAt: Date.now() }); }
    catch (e: any) { setError(String(e?.message ?? e)); }
    finally { setBusy(false); }
  };
  // Auto Demo requests the same real workflow as the button; no canned report is shown.
  useEffect(() => { if (coachRequest > handled && started && !busy) { handled = coachRequest; generate(); } }, [coachRequest]);
  const r = result?.report;
  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1">
            <div className="label text-cyan-300">Microsoft Agent Framework · Performance Desk</div>
            <h1 className="mt-1 font-display text-3xl font-bold text-white">Coach & analyst report</h1>
            <p className="mt-1 text-sm text-slate-400">Evidence analyst → coach strategist → claim verifier → PDF publisher</p>
          </div>
          <button className="btn-primary" onClick={generate} disabled={busy || !started} title={started ? "" : "Start the match first"}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} {r ? "Regenerate report" : "Generate report"}
          </button>
          {r?.download_url && <a className="btn" href={r.download_url}><Download size={14} /> Download PDF</a>}
        </div>
        {error && <div className="mt-4 rounded-xl bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
        {!r && !busy && <div className="glass mt-8 grid min-h-64 place-items-center p-12 text-center text-slate-400">
          <div><Network className="mx-auto mb-3 text-cyan-300" size={32} /><p>Run a real Microsoft Agent Framework workflow over the match evidence.</p>
          <p className="mt-1 text-xs">Every number and cited minute is checked before the PDF is published.</p></div>
        </div>}
        {busy && <div className="glass mt-8 grid min-h-64 place-items-center text-slate-300"><div className="text-center"><Loader2 className="mx-auto mb-3 animate-spin text-cyan-300" />Agents are collecting, coaching, verifying and publishing…</div></div>}
        {r && !busy && <>
          <div className="mt-5 grid grid-cols-4 gap-2">
            {(result.stages ?? []).map((s: any, i: number) => <div key={s.agent} className="glass p-3">
              <div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-full bg-cyan-400/15 font-mono text-xs text-cyan-200">{i + 1}</span><span className="font-mono text-xs text-white">{s.agent}</span></div>
              <div className="mt-2 text-[11px] text-emerald-300">✓ {s.status}</div><div className="text-[10px] text-slate-500">{s.latency_ms} ms · {s.model}</div>
            </div>)}
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <Panel title="Executive summary" className="lg:col-span-2"><p className="p-4 text-[14px] leading-6 text-slate-100">{r.executive_summary}</p></Panel>
            <List title="Tactical diagnosis" items={r.tactical_diagnosis} />
            <List title="Player notes" items={r.player_notes} />
            <List title="Priority recommendations" items={r.recommendations} />
            <List title="Training plan" items={r.training_plan} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className={`chip ${r.verification?.passed ? "text-emerald-300" : "text-amber-300"}`}><BadgeCheck size={13} /> {r.verification?.passed ? "All claims verified" : `Verified · ${r.verification?.corrected?.length ?? 0} unsupported item(s) replaced with evidence-only text`}</span>
            <span className="chip text-cyan-200"><ShieldCheck size={13} /> Evidence locked</span>
            <span className="chip">{result.framework} · {Math.round(result.duration_ms)} ms</span>
            <span className="chip">A2A + {result.mcp_tools} MCP tools</span>
          </div>
        </>}
      </div>
    </div>
  );
}

const PRIORITY: Record<string, string> = { high: "bg-rose-400/15 text-rose-200", medium: "bg-amber-400/15 text-amber-200", low: "bg-slate-400/15 text-slate-200" };

function Item({ item }: { item: any }) {
  if (typeof item === "string") return <span>{item}</span>;
  if (item.player) return <span><b className="text-white">{item.player}</b> — {item.note}</span>;
  if (item.action) return <span><span className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${PRIORITY[item.priority] ?? PRIORITY.low}`}>{item.priority}</span>
    <b className="text-white">{item.action}</b><span className="mt-1 block text-[12px] text-slate-400">Why: {item.rationale}</span></span>;
  if (item.theme) return <span><b className="text-white">{item.theme}</b><span className="mt-1 block">{item.drill}</span>
    <span className="mt-1 block text-[12px] text-emerald-300/90">Target: {item.success_measure}</span></span>;
  return <span>{Object.values(item).join(" · ")}</span>;
}

function List({ title, items = [] }: { title: string; items: any[] }) {
  return <Panel title={title}><div className="space-y-2 p-4">{items.map((item, i) =>
    <div key={i} className="flex gap-2 rounded-lg bg-white/[0.025] p-2.5 text-[13px] leading-5 text-slate-200"><span className="font-mono text-cyan-300">{String(i + 1).padStart(2, "0")}</span><Item item={item} /></div>
  )}</div></Panel>;
}
