import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, Trophy } from "lucide-react";
import { useStore } from "../lib/store";

export default function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismiss);
  return (
    <div className="pointer-events-none fixed left-1/2 top-20 z-50 flex w-[440px] -translate-x-1/2 flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} layout initial={{ opacity: 0, y: -16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -10 }} onClick={() => dismiss(t.id)}
                      className="glass-strong pointer-events-auto relative overflow-hidden px-4 py-3"
                      style={{ boxShadow: `0 0 0 1px ${t.color ?? "#22d3ee"}55, 0 20px 50px -20px ${t.color ?? "#22d3ee"}` }}>
            <div className="absolute inset-x-0 top-0 h-[2px] overflow-hidden"><div className="h-full w-1/2 animate-sweep" style={{ background: t.color ?? "#22d3ee" }} /></div>
            <div className="flex items-start gap-3">
              <div className="mt-0.5" style={{ color: t.color ?? "#22d3ee" }}>{t.kind === "goal" ? <Trophy size={18} /> : <Sparkles size={18} />}</div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: t.color ?? "#22d3ee" }}>
                  {t.kind === "pattern" ? "AI detected a tactical pattern" : t.kind === "goal" ? "Goal" : "Update"}
                </div>
                <div className="font-display text-sm font-semibold capitalize text-white">{t.title.toLowerCase()}</div>
                {t.body && <div className="mt-0.5 text-xs text-slate-300">{t.body}</div>}
              </div>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
