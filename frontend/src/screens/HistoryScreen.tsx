import { useMemo, useState } from "react";
import { History, Search } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { replayInsight } from "../lib/replay";
import { MiniPitch } from "./TacticsScreen";
import { Panel } from "../components/ui";

const ZONES: Record<string, [number, number, number, number]> = {
  HIGH_PRESS: [70, 105, 0, 68], FLANK_OVERLOAD: [52.5, 105, 0, 22.7], DEEP_BLOCK: [0, 35, 0, 68],
  TRANSITION_VULNERABILITY: [0, 52.5, 0, 68], MIDFIELD_SUPERIORITY: [35, 70, 12, 56],
};
const COLORS: Record<string, string> = { HIGH_PRESS: "#FACC15", FLANK_OVERLOAD: "#22D3EE", DEEP_BLOCK: "#A78BFA", TRANSITION_VULNERABILITY: "#F97316", MIDFIELD_SUPERIORITY: "#34D399" };

export default function HistoryScreen() {
  const { insights, matchId, profile, set } = useStore();
  const withCmp = useMemo(() => insights.filter((i) => i.statistics?.comparison).reverse(), [insights]);
  const [selId, setSelId] = useState<string | null>(null);
  const sel = withCmp.find((i) => i.insight_id === selId) ?? withCmp[0];
  const cmp = sel?.statistics?.comparison;
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any>(null);
  const [answer, setAnswer] = useState<any>(null);
  const zonesNow = (sel?.visualization ?? []).filter((c) => c.type === "highlight_zone");
  const thenPatterns: string[] = cmp?.shared_patterns?.length ? cmp.shared_patterns : [];

  const showGhost = () => {
    if (!sel) return;
    const ghost = thenPatterns.map((p) => {
      const [x0, x1, y0, y1] = ZONES[p] ?? [0, 105, 0, 68];
      return { type: "highlight_zone", zone: { x0, x1, y0, y1 }, color: "#E879F9", label: `${cmp.title.split("—")[0].trim()} · ${p.replaceAll("_", " ").toLowerCase()}` };
    });
    replayInsight(sel).then(() => useStore.getState().set({ scene: { ...useStore.getState().scene, ghost } }));
  };
  const ask = async () => setAnswer((await api.ask(matchId, "Compare this with a historical match", profile.user_id, "tactical_analyst")).answer);

  return (
    <div className="grid h-full grid-cols-[320px_1fr_360px] gap-3 p-3">
      <Panel title="Moments with historical evidence">
        <div className="h-full space-y-1.5 overflow-y-auto p-2">
          {withCmp.map((i) => (
            <button key={i.insight_id} onClick={() => setSelId(i.insight_id)}
                    className={`w-full rounded-lg px-3 py-2 text-left ${sel?.insight_id === i.insight_id ? "bg-cyan-400/10" : "hover:bg-white/5"}`}>
              <div className="font-mono text-[11px] text-slate-500">{i.minute}'</div>
              <div className="text-[13px] text-white">{i.headline}</div>
              <div className="text-[11px] text-violet-300">↔ {i.statistics.comparison.title}</div>
            </button>
          ))}
          {!withCmp.length && <div className="p-3 text-[12px] text-slate-500">Comparisons appear when Agentic RAG finds a sufficiently similar historical match (pattern starts, goals).</div>}
        </div>
      </Panel>
      <Panel title="Now vs then" right={sel && <div className="flex gap-1"><button className="btn" onClick={showGhost}>Overlay in 3D</button><button className="btn" onClick={ask}>Ask the analyst</button></div>}>
        {sel && cmp ? (
          <div className="h-full overflow-y-auto p-5">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="label mb-1 text-cyan-300">Now · {sel.minute}'</div>
                <MiniPitch className="w-full">
                  {zonesNow.map((z, i) => <rect key={i} x={z.zone.x0} y={z.zone.y0} width={z.zone.x1 - z.zone.x0} height={z.zone.y1 - z.zone.y0} fill={z.color} opacity={0.3} stroke={z.color} strokeWidth={0.5} />)}
                </MiniPitch>
                <div className="mt-2 font-display text-[15px] font-semibold text-white">{sel.headline}</div>
                <div className="mt-1 text-[13px] text-slate-300">{sel.explanations.advanced}</div>
              </div>
              <div>
                <div className="label mb-1 text-fuchsia-300">Then · {cmp.title}</div>
                <MiniPitch className="w-full">
                  {thenPatterns.map((p) => { const [x0, x1, y0, y1] = ZONES[p] ?? [0, 105, 0, 68]; return <rect key={p} x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill={COLORS[p] ?? "#E879F9"} opacity={0.25} stroke="#E879F9" strokeDasharray="1.5 1" strokeWidth={0.5} />; })}
                </MiniPitch>
                <div className="mt-2 text-[13px] text-slate-300">{cmp.then}</div>
                <div className="mt-2 text-[11px] text-slate-500">{cmp.source}{cmp.synthetic ? " — synthetic demo archive" : ""} · relevance {cmp.rerank_score}</div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {cmp.shared_patterns?.map((p: string) => <span key={p} className="chip text-cyan-200">shared pattern · {p.replaceAll("_", " ").toLowerCase()}</span>)}
              {cmp.shared_teams?.map((t: string) => <span key={t} className="chip">same team · {t}</span>)}
              {cmp.why_selected?.map((w: string) => <span key={w} className="chip text-slate-400">{w}</span>)}
            </div>
            {sel.historical_note && <div className="mt-3 flex gap-2 rounded-lg bg-violet-500/10 p-3 text-[13px] text-violet-100"><History size={15} className="mt-0.5" />{sel.historical_note}</div>}
            {answer && <div className="mt-3 rounded-lg border border-cyan-300/20 bg-cyan-400/5 p-3"><div className="font-semibold text-white">{answer.headline}</div><div className="mt-1 text-[13px] text-slate-300">{answer.statistics?.answer}</div>
              <button className="btn mt-2" onClick={() => set({ whyId: answer.insight_id })}>Why?</button></div>}
          </div>
        ) : <div className="grid h-full place-items-center text-slate-500">No comparison selected yet.</div>}
      </Panel>
      <Panel title="Knowledge base search (vector)">
        <div className="flex h-full flex-col p-3">
          <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); setRes(await api.knowledge(q)); }}>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. full-back overlap crosses"
                   className="h-9 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 text-[13px] outline-none focus:border-cyan-300/50" />
            <button className="btn"><Search size={14} /></button>
          </form>
          <div className="mt-3 flex-1 space-y-2 overflow-y-auto">
            {res && [...res.historical_matches, ...res.knowledge_documents].map((d: any) => (
              <div key={d.doc_id} className="rounded-lg bg-white/[0.03] p-2.5">
                <div className="flex justify-between text-[12px]"><span className="font-medium text-white">{d.title}</span><span className="font-mono text-cyan-300">{d.score}</span></div>
                <div className="mt-1 line-clamp-3 text-[11.5px] text-slate-400">{d.text}</div>
              </div>
            ))}
          </div>
        </div>
      </Panel>
    </div>
  );
}
