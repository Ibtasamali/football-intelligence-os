import { AnimatePresence, motion } from "framer-motion";
import { Square } from "lucide-react";
import { useStore } from "../lib/store";
import { stopDemo } from "../lib/autodemo";

export default function DemoBar() {
  const demo = useStore((s) => s.demo);
  const onLive = useStore((s) => s.screen === "live");
  return (
    <AnimatePresence>
      {demo && (
        <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
          className={`fixed left-1/2 z-[60] w-[min(760px,calc(100vw-120px))] -translate-x-1/2 ${onLive ? "top-[72px]" : "bottom-4"}`}>
          <div className="glass-strong overflow-hidden border-cyan-300/30 shadow-glow">
            <div className="h-1 bg-white/10">
              <motion.div className="h-full bg-gradient-to-r from-cyan-400 to-indigo-400" animate={{ width: `${(demo.step / demo.total) * 100}%` }} />
            </div>
            <div className="flex items-center gap-3 px-4 py-2.5">
              <span className="rounded-md bg-cyan-400/15 px-2 py-0.5 font-mono text-[11px] font-bold text-cyan-200">AUTO DEMO {demo.step}/{demo.total}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-display text-[15px] font-semibold text-white">{demo.caption}</div>
                {demo.sub && <div className="truncate text-[12px] text-slate-400">{demo.sub}</div>}
              </div>
              {demo.running && <button className="btn" onClick={stopDemo}><Square size={12} /> Stop</button>}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
