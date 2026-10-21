import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, BookOpen, Brain, CircleAlert, Cpu, GitBranch, X } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { Confidence, pct } from "./ui";

export default function WhyDrawer() {
  const whyId = useStore((s) => s.whyId);
  const set = useStore((s) => s.set);
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    setData(null);
    if (whyId) api.why(whyId).then(setData).catch(() => setData({ error: true }));
  }, [whyId]);
  return (
    <AnimatePresence>
      {whyId && (
        <motion.aside initial={{ x: 520 }} animate={{ x: 0 }} exit={{ x: 520 }} transition={{ type: "spring", damping: 28, stiffness: 260 }}
          className="glass-strong fixed bottom-24 right-3 top-[76px] z-40 flex w-[min(500px,calc(100vw-100px))] flex-col overflow-hidden">
          <header className="flex items-start gap-3 border-b border-white/10 p-4">
            <div className="flex-1">
              <div className="label text-cyan-300">Explainable AI · why the system believes this</div>
              <h2 className="mt-1 font-display text-lg font-semibold text-white">{data?.headline ?? "Loading evidence…"}</h2>
            </div>
            {data && <Confidence value={data.confidence ?? 0} size={44} />}
            <button className="btn" onClick={() => set({ whyId: null })}><X size={14} /></button>
          </header>
          {data && !data.error && (
            <div className="flex-1 space-y-4 overflow-y-auto p-4 text-[13px]">
              <Section icon={<BadgeCheck size={14} />} title="Verified claims">
                {data.claims?.length ? data.claims.map((c: any, i: number) => (
                  <div key={i} className="mb-2 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] p-2.5">
                    <div className="text-slate-100">{c.text}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {c.event_ids?.map((e: string) => <span key={e} className="chip font-mono text-[10px]">#{e.split("-e").pop()}</span>)}
                      {c.metric_refs?.slice(0, 3).map((m: string) => <span key={m} className="chip font-mono text-[10px] text-cyan-200">{m.split(".").slice(-2).join(".")}</span>)}
                    </div>
                  </div>)) : <Empty text="No atomic claims recorded." />}
                {data.verification?.issues?.length > 0 && (
                  <div className="rounded-lg border border-amber-400/20 bg-amber-400/[0.06] p-2.5 text-amber-200">
                    <div className="mb-1 flex items-center gap-1 font-semibold"><CircleAlert size={13} /> Rejected / corrected by Fact Verification</div>
                    {data.verification.issues.slice(0, 5).map((s: string, i: number) => <div key={i} className="text-[12px]">• {s}</div>)}
                  </div>
                )}
              </Section>
              <Section icon={<GitBranch size={14} />} title="Source events">
                <div className="space-y-1">
                  {data.evidence_events?.slice(-10).map((e: any) => (
                    <div key={e.event_id} className="flex gap-2 font-mono text-[11px]">
                      <span className="text-slate-500">#{e.seq}</span><span className="text-cyan-200">{e.clock}</span>
                      <span className="text-slate-200">{e.type}</span><span className="text-slate-400">{e.player}</span>
                      {e.outcome && <span className="text-slate-500">{e.outcome}</span>}{e.xg != null && <span className="text-yellow-300">xG {e.xg}</span>}
                    </div>))}
                </div>
              </Section>
              {Object.keys(data.statistics ?? {}).length > 0 && (
                <Section icon={<Cpu size={14} />} title="Supporting statistics">
                  <div className="grid grid-cols-2 gap-1">
                    {Object.entries(data.statistics).slice(0, 16).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2 rounded bg-white/[0.03] px-2 py-1 font-mono text-[10.5px]">
                        <span className="truncate text-slate-400">{k.split(".").slice(-2).join(".")}</span><span className="text-white">{String(v)}</span>
                      </div>))}
                  </div>
                </Section>
              )}
              <Section icon={<BookOpen size={14} />} title="Agentic RAG evidence">
                {data.retrieved_documents?.length ? data.retrieved_documents.map((d: any) => (
                  <div key={d.doc_id} className="mb-1.5 rounded-lg bg-white/[0.03] p-2">
                    <div className="flex justify-between"><span className="font-medium text-white">{d.title}</span><span className="font-mono text-[10px] text-cyan-300">{d.rerank_score}</span></div>
                    <div className="text-[11px] text-slate-400">{d.source}{d.synthetic ? " · synthetic archive" : ""} {d.why_selected?.length ? `· ${d.why_selected.join(", ")}` : ""}</div>
                  </div>)) : <Empty text="Retrieval was not needed — live context (CAG) was sufficient." />}
                {data.rag_trace && <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-black/40 p-2 font-mono text-[10px] text-slate-400">{data.rag_trace.join("\n")}</pre>}
              </Section>
              {data.memories?.length > 0 && (
                <Section icon={<Brain size={14} />} title="Long-term memory (MAG)">
                  {data.memories.map((m: any) => <div key={m.memory_id} className="mb-1 text-[12px] text-slate-300">• {m.text} <span className="text-slate-500">({m.source})</span></div>)}
                </Section>
              )}
              {data.predictions?.length > 0 && (
                <Section icon={<Cpu size={14} />} title="Predictions (probabilistic, not facts)">
                  {data.predictions.map((p: any) => (
                    <div key={p.label} className="mb-1.5">
                      <div className="flex justify-between text-[12px]"><span>{p.label}</span><span className="font-mono text-amber-300">{pct(p.probability)}</span></div>
                      <div className="h-1 rounded bg-white/5"><div className="h-full rounded bg-amber-400" style={{ width: pct(p.probability) }} /></div>
                      <div className="text-[10.5px] text-slate-500">{p.basis}</div>
                    </div>))}
                </Section>
              )}
              <Section icon={<GitBranch size={14} />} title="LangGraph path & agents">
                <div className="flex flex-wrap gap-1">
                  {data.graph_path?.map((p: string, i: number) => <span key={i} className="chip font-mono text-[10px] text-cyan-100">{i + 1}. {p}</span>)}
                </div>
                <div className="mt-2 text-[11px] text-slate-400">Model: <span className="text-white">{data.model}</span> · {data.agents_used?.length} agents contributed</div>
                <div className="mt-1 flex flex-wrap gap-1">{data.agents_used?.map((a: string) => <span key={a} className="chip text-[10px]">{a}</span>)}</div>
                {data.routing?.reasons && <div className="mt-2 text-[11px] text-slate-400">Router: {data.routing.reasons.join(" · ")}</div>}
              </Section>
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-1.5 text-cyan-300">{icon}<span className="label text-cyan-300">{title}</span></div>
      {children}
    </section>
  );
}
const Empty = ({ text }: { text: string }) => <div className="text-[12px] text-slate-500">{text}</div>;
