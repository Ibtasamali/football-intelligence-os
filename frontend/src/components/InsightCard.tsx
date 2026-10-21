import { motion } from "framer-motion";
import { BadgeCheck, Box, HelpCircle, History, Volume2 } from "lucide-react";
import { useStore } from "../lib/store";
import type { Insight } from "../lib/types";
import { replayInsight } from "../lib/replay";
import { speak } from "../lib/voice";
import { langMeta, useLocalized } from "../lib/i18n";
import { Badge, Confidence, pct } from "./ui";

export default function InsightCard({ ins, compact, translate = true }: { ins: Insight; compact?: boolean; translate?: boolean }) {
  const profile = useStore((s) => s.profile);
  const featured = useStore((s) => s.featuredId === ins.insight_id);
  const set = useStore((s) => s.set);
  const level = (ins.statistics?.level as string) ?? profile.knowledge_level;
  const text = ins.statistics?.answer && ins.category === "ANSWER" ? ins.statistics.answer : ins.explanations?.[level] || ins.explanations?.intermediate;
  const perspective = profile.favorite_team_id ? ins.perspectives?.[profile.favorite_team_id] : null;
  const verified = ins.verification?.passed !== false;
  const preds = (ins.predictions ?? []).filter((p) => p.probability >= 0.15).slice(0, 2);
  const lang = profile.language || "en";
  const loc = useLocalized(ins, lang, level, profile.persona, translate);
  const tr = loc && loc.language !== "en" ? loc : null;
  const dir = tr && langMeta(tr.language)?.rtl ? "rtl" : undefined;
  const listen = () => tr ? speak(tr.voice || tr.commentary || tr.headline, profile.persona, tr.language, langMeta(tr.language)?.locale)
    : speak(ins.voice_scripts?.[profile.persona] || ins.commentary || ins.headline, profile.persona);
  return (
    <motion.article layout initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}
      className={`group relative overflow-hidden rounded-xl border p-3.5 transition ${featured ? "border-cyan-300/40 bg-cyan-400/[0.06] shadow-glow" : "border-white/[0.06] bg-white/[0.025] hover:border-white/15"}`}>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-mono text-[11px] text-slate-400">{String(ins.minute).padStart(2, "0")}:{String(ins.second).padStart(2, "0")}</span>
        <Badge category={ins.category} />
        {ins.provenance?.cache_hit && <span className="chip text-[10px] text-emerald-300">shared cache · 0 tokens</span>}
        <div className="ml-auto"><Confidence value={ins.provenance?.confidence ?? 0.6} size={28} /></div>
      </div>
      <h3 dir={dir} className="font-display text-[15px] font-semibold leading-snug text-white">{tr?.headline || ins.headline}</h3>
      {!compact && <p dir={dir} className="mt-1.5 text-[13px] leading-relaxed text-slate-300">{tr?.explanation || text}</p>}
      {!compact && lang !== "en" && (
        <div className="mt-1 text-[10px] text-slate-500">
          {tr ? <>🌐 {langMeta(tr.language)?.native} · translated after fact-check · numbers re-verified{tr.cached ? " · shared cache" : ""}</>
              : loc && !loc.verified ? "Translation failed verification — showing verified English"
              : translate ? "Translating…" : "Showing English (older card)"}
        </div>
      )}
      {!compact && perspective && <p className="mt-1.5 text-[12px] italic text-cyan-200/80">{perspective}</p>}
      {!compact && ins.historical_note && (
        <p dir={dir} className="mt-2 flex gap-1.5 rounded-lg bg-violet-500/10 px-2 py-1.5 text-[12px] text-violet-200"><History size={13} className="mt-0.5 shrink-0" />{tr?.historical_note || ins.historical_note}</p>
      )}
      {!compact && preds.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {preds.map((p) => (
            <span key={p.label} className="chip text-[11px] text-amber-200" title={`Prediction · ${p.basis}`}>
              <span className="text-[9px] font-bold uppercase text-amber-400">pred</span> {p.label} · {pct(p.probability)}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2.5 flex items-center gap-1.5">
        <button className="btn" onClick={() => set({ whyId: ins.insight_id })}><HelpCircle size={13} /> Why?</button>
        {ins.visualization?.length > 0 && <button className="btn" onClick={() => replayInsight(ins)}><Box size={13} /> Replay 3D</button>}
        <button className="btn" onClick={listen}><Volume2 size={13} /></button>
        <span className={`ml-auto flex items-center gap-1 text-[10px] ${verified ? "text-emerald-300" : "text-amber-300"}`} title="Fact Verification Agent">
          <BadgeCheck size={13} /> {verified ? `${ins.claims?.length ?? 0} claims verified` : "partially verified"}
        </span>
      </div>
    </motion.article>
  );
}
