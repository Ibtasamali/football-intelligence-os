import { AnimatePresence, motion } from "framer-motion";
import { Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import { useStore } from "../lib/store";

/** Live strip of the most recent agent executions — shows the multi-agent system working in real time. */
export default function AgentTicker() {
  const agents = useStore((s) => s.agents);
  const runs = useStore((s) => s.runs);
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((x) => x + 1), 500);
    return () => clearInterval(id);
  }, []);
  const recent = Object.values(agents).filter((a) => Date.now() - a.at < 3500).sort((a, b) => b.at - a.at).slice(0, 7);
  const run = runs[0];
  return (
    <div className="glass flex h-11 items-center gap-3 overflow-hidden px-3">
      <div className="flex shrink-0 items-center gap-1.5 text-cyan-300"><Cpu size={14} /><span className="label text-cyan-300">Agents</span></div>
      {run && (
        <div className="shrink-0 whitespace-nowrap text-[11px] text-slate-400">
          {run.done ? "last run" : <span className="text-cyan-200">running</span>} · {run.category?.replaceAll("_", " ").toLowerCase()} ·{" "}
          <span className="font-mono">sig {run.significance?.toFixed(2)}</span>
          {run.plan && <> · tier <span className="font-mono text-white">{run.plan.model_tier}</span></>}
          {run.done && <> · <span className="font-mono">{Math.round(run.duration_ms ?? 0)}ms</span>{run.cache_hit ? " · cache hit" : ""}</>}
        </div>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
        <AnimatePresence initial={false}>
          {recent.map((a) => (
            <motion.span key={a.agent + a.at} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className={`chip h-6 shrink-0 whitespace-nowrap font-mono text-[10.5px] ${a.status === "failed" ? "text-red-300" : a.model?.includes("gpt") ? "text-amber-200" : "text-emerald-200"}`}>
              {a.agent} <span className="text-slate-500">{Math.round(a.latency_ms)}ms</span>
              {a.tokens > 0 && <span className="text-amber-300">{a.tokens}t</span>}
            </motion.span>
          ))}
        </AnimatePresence>
        {!recent.length && <span className="truncate whitespace-nowrap text-[11px] text-slate-500">Routine play — fast path only, no agents or tokens spent.</span>}
      </div>
    </div>
  );
}
