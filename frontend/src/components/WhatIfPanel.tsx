import { motion } from "framer-motion";
import { FlaskConical, Loader2, RotateCcw, X } from "lucide-react";
import { useStore } from "../lib/store";
import { exitWhatIf, resetWhatIf } from "../lib/whatif";

function Row({ label, before, after, unit = "", better = "up" }: { label: string; before: number | undefined; after: number | undefined; unit?: string; better?: "up" | "down" }) {
  const d = (after ?? 0) - (before ?? 0);
  const good = better === "up" ? d > 0 : d < 0;
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-[12.5px]">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono text-slate-300">
        {before ?? "–"}{unit} → <span className="text-white">{after ?? "–"}{unit}</span>
        {d !== 0 && <span className={`ml-1.5 ${good ? "text-emerald-300" : "text-rose-300"}`}>({d > 0 ? "+" : ""}{Math.round(d * 10) / 10})</span>}
      </span>
    </div>
  );
}

export default function WhatIfPanel() {
  const wi = useStore((s) => s.whatIf);
  if (!wi.active) return null;
  const r = wi.result;
  const b = r?.before, a = r?.after ?? r?.before;
  const moved = Object.keys(wi.moves).length;
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="glass-strong absolute bottom-3 left-3 z-20 w-[360px] max-w-[calc(100%-24px)] p-4">
      <div className="flex items-center gap-2">
        <FlaskConical size={16} className="text-fuchsia-300" />
        <div className="flex-1">
          <div className="label text-fuchsia-300">What-if tactical lab</div>
          <div className="text-[12px] text-slate-400">Frozen at {wi.clock} · {r ? `${r.attacking_name} in possession` : "loading…"}</div>
        </div>
        {wi.loading && <Loader2 size={15} className="animate-spin text-slate-400" />}
        <button className="btn" onClick={resetWhatIf} title="Reset"><RotateCcw size={13} /></button>
        <button className="btn" onClick={exitWhatIf} title="Exit"><X size={13} /></button>
      </div>
      {!moved && <div className="mt-3 rounded-lg bg-fuchsia-500/10 p-2.5 text-[12.5px] text-fuchsia-100">👆 <b>Drag any player</b> on the pitch. The AI recomputes who controls the space, the passing options and the danger.</div>}
      {b && (
        <div className="mt-3 border-t border-white/10 pt-2">
          <Row label="Dangerous space (attack)" before={b.dangerous_space_pct} after={a.dangerous_space_pct} unit="%" />
          <Row label="Final-third space" before={b.final_third_space_m2} after={a.final_third_space_m2} unit=" m²" />
          <Row label="Open passing options" before={b.open_passing_options} after={a.open_passing_options} />
          <Row label="Defensive line height" before={b.defence_shape?.line_height} after={a.defence_shape?.line_height} unit=" m" better="down" />
          <div className="mt-1 text-[11px] text-slate-500">Channels (attackers v defenders): {Object.entries(a.channels ?? {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>
        </div>
      )}
      {r?.explanation && moved > 0 && (
        <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.03] p-2.5">
          <div className="font-display text-[14px] font-semibold text-white">{r.explanation.headline}</div>
          <div className="mt-1 text-[12.5px] leading-relaxed text-slate-300">{r.explanation.text}</div>
          <div className="mt-1 text-[10px] text-slate-500">{r.explanation.verified ? "✓ numbers verified against the model" : "template explanation"} · pitch-control model</div>
        </div>
      )}
      <div className="mt-2 text-[10.5px] text-slate-500">Colour = space each team controls · green lanes open, red blocked · pink = original position</div>
    </motion.div>
  );
}
