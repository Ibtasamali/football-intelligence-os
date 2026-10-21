import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { Panel, Stat } from "../components/ui";

const FAMILY_COLOR: Record<string, string> = {
  perception: "#22D3EE", tactical: "#FACC15", entity: "#A78BFA", knowledge: "#34D399", reasoning: "#F97316", experience: "#F472B6",
};
const EVENT_NODES = ["ingest_event", "classify_event", "check_cache", "route_agents", "run_analysis", "retrieve_memory", "retrieve_context",
  "compare_history", "predict_next_state", "generate_explanation", "verify_claims", "personalize", "generate_3d_command", "generate_voice", "publish_insight"];

export default function AgentsScreen() {
  const live = useStore((s) => s.agents);
  const runs = useStore((s) => s.runs);
  const [obs, setObs] = useState<any>(null);
  const [catalog, setCatalog] = useState<any[]>([]);
  useEffect(() => {
    api.catalog().then((c) => setCatalog(c.agents));
    const load = () => api.observability().then(setObs).catch(() => {});
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);
  const c = obs?.counters ?? {};
  const stats: Record<string, any> = Object.fromEntries((obs?.agents ?? []).map((a: any) => [a.agent, a]));
  const lastDone = runs.find((r) => r.done && r.graph_path?.length);
  const path = new Set((lastDone?.graph_path ?? []).map((p: string) => p.split(":")[0]));
  const families = ["perception", "tactical", "entity", "knowledge", "reasoning", "experience"];
  return (
    <div className="grid h-full grid-rows-[auto_auto_1fr] gap-3 overflow-hidden p-3">
      <div className="grid grid-cols-8 gap-2">
        <Stat label="Events ingested" value={c.events_ingested ?? 0} />
        <Stat label="Zero-token events" value={`${obs?.events_without_llm_pct ?? 100}%`} accent="#34D399" sub="fast path / deterministic" />
        <Stat label="Deep analyses" value={c.events_analysed ?? 0} sub={`${c.events_coalesced ?? 0} coalesced`} />
        <Stat label="LLM calls" value={c.llm_calls ?? 0} sub={`${Math.round((c.tokens_used ?? 0) / 1000)}k tokens`} accent="#FACC15" />
        <Stat label="Cache hits" value={(c.llm_cache_hits ?? 0) + (c.insight_cache_hits ?? 0) + (c.answer_cache_hits ?? 0) + (c.restyles_zero_token ?? 0)} sub="LLM · insight · answer · restyle" accent="#22D3EE" />
        <Stat label="RAG retrievals" value={c.rag_retrievals ?? 0} sub={`${c.rag_replans ?? 0} re-plans`} />
        <Stat label="Verification" value={c.verification_retries ?? 0} sub="retries after rejected claims" accent="#F97316" />
        <Stat label="Worker pool" value={`${obs?.workers?.active ?? 0}/${obs?.workers?.workers ?? 0}`} sub={`${obs?.workers?.queued ?? 0} queued · ${c.tasks_deduplicated ?? 0} dedup`} />
      </div>
      <Panel title={`LangGraph · last run ${lastDone ? `(${lastDone.category?.toLowerCase()} · ${Math.round(lastDone.duration_ms ?? 0)}ms · ${lastDone.tokens ?? 0} tokens)` : ""}`}>
        <div className="flex flex-wrap items-center gap-1.5 p-3">
          {EVENT_NODES.map((n, i) => (
            <div key={n} className="flex items-center gap-1.5">
              <motion.span animate={{ opacity: path.has(n) ? 1 : 0.3 }}
                className={`rounded-md border px-2 py-1 font-mono text-[11px] ${path.has(n) ? "border-cyan-300/50 bg-cyan-400/10 text-cyan-100" : "border-white/10 text-slate-500"}`}>{n}</motion.span>
              {i < EVENT_NODES.length - 1 && <span className="text-slate-600">→</span>}
            </div>
          ))}
          {lastDone?.plan && <div className="mt-2 w-full text-[11px] text-slate-400">Router: {lastDone.plan.reasons?.join(" · ")}</div>}
        </div>
      </Panel>
      <div className="grid min-h-0 grid-cols-[1fr_380px] gap-3">
        <div className="min-h-0 overflow-y-auto pr-1">
          {families.map((f) => (
            <div key={f} className="mb-3">
              <div className="label mb-1.5" style={{ color: FAMILY_COLOR[f] }}>{f} agents</div>
              <div className="grid grid-cols-3 gap-2 xl:grid-cols-5">
                {catalog.filter((a) => a.family === f).map((a) => {
                  const s = stats[a.name];
                  const l = live[a.name];
                  const hot = l && Date.now() - l.at < 2500;
                  return (
                    <motion.div key={a.name} animate={{ boxShadow: hot ? `0 0 0 1px ${FAMILY_COLOR[f]}, 0 0 24px ${FAMILY_COLOR[f]}55` : "0 0 0 1px rgba(255,255,255,.06)" }}
                      className="rounded-xl bg-white/[0.025] p-2.5" title={a.description}>
                      <div className="flex items-center justify-between">
                        <span className="truncate font-mono text-[11.5px] text-white">{a.name}</span>
                        <span className={`h-2 w-2 rounded-full ${hot ? "animate-pulse" : ""}`} style={{ background: s?.failures ? "#f87171" : s?.runs ? FAMILY_COLOR[f] : "#334155" }} />
                      </div>
                      <div className="mt-1 text-[10px] text-slate-500">{a.uses_llm ? "LLM · tiered" : "deterministic · 0 tokens"}</div>
                      <div className="mt-1.5 grid grid-cols-3 gap-1 font-mono text-[10px]">
                        <span className="text-slate-400">runs <span className="text-white">{s?.runs ?? 0}</span></span>
                        <span className="text-slate-400">{s ? Math.round(s.avg_latency_ms) : 0}<span className="text-slate-600">ms</span></span>
                        <span className="text-slate-400">conf <span className="text-white">{s ? Math.round(s.avg_confidence * 100) : 0}</span></span>
                      </div>
                      {s?.tokens > 0 && <div className="font-mono text-[10px] text-amber-300">{s.tokens} tokens · {s.last_model}</div>}
                    </motion.div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <Panel title="Run log (agent_run_id traced)">
          <div className="h-full space-y-1 overflow-y-auto p-3 font-mono text-[10.5px]">
            {runs.map((r) => (
              <div key={r.run_id} className="rounded-md bg-white/[0.03] px-2 py-1.5">
                <div className="flex justify-between"><span className="text-cyan-200">{r.category}</span><span className={r.done ? "text-emerald-300" : "text-amber-300"}>{r.done ? `${Math.round(r.duration_ms ?? 0)}ms` : "running…"}</span></div>
                <div className="truncate text-slate-500">{r.run_id} · sig {r.significance?.toFixed(2)} · {r.plan?.model_tier ?? "…"}{r.cache_hit ? " · cache" : ""}</div>
                <div className="truncate text-slate-400">{r.reasons?.join(", ")}</div>
              </div>
            ))}
            {obs?.models && Object.entries(obs.models).map(([m, u]: any) => (
              <div key={m} className="mt-2 text-slate-400">model {m}: {u.calls} calls · {u.tokens} tokens · {u.avg_latency_ms}ms avg</div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
