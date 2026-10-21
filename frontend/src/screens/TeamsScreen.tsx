import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { Panel, VersusBar, pct } from "../components/ui";

export default function TeamsScreen() {
  const { matchId, teams, homeId: H, awayId: A } = useStore();
  const [data, setData] = useState<Record<string, any>>({});
  useEffect(() => {
    Promise.all([H, A].map((t) => api.team(t, matchId))).then(([h, a]) => setData({ [H]: h, [A]: a })).catch(() => {});
  }, [matchId, H, A]);
  const h = data[H], a = data[A];
  const hc = teams[H]?.colors.primary ?? "#3BA4F6", ac = teams[A]?.colors.primary ?? "#F2555A";
  if (!h || !a) return <div className="grid h-full place-items-center text-slate-500">Loading teams…</div>;
  const rows: [string, string, ((v: number) => string)?, boolean?][] = [
    ["possession", "Possession", pct], ["xg", "Expected goals"], ["shots", "Shots"], ["shots_on_target", "On target"],
    ["field_tilt", "Field tilt", pct], ["ppda", "PPDA (lower = more press)", undefined, true], ["pass_completion", "Pass completion", pct],
    ["progressive_passes", "Progressive passes"], ["final_third_entries", "Final-third entries"], ["high_turnovers", "High turnovers"],
    ["defensive_line_height", "Defensive line height (m)"], ["attacking_width", "Attacking width (m)"], ["avg_transition_seconds", "Avg transition (s)", undefined, true],
  ];
  return (
    <div className="grid h-full grid-cols-[1fr_1.1fr_1fr] gap-3 p-3">
      {[h, a].map((d, idx) => (
        <Panel key={idx} title={d.team.name} className={idx === 1 ? "order-3" : ""}>
          <div className="h-full overflow-y-auto p-5">
            <div className="flex items-center gap-3">
              <div className="grid h-14 w-14 place-items-center rounded-2xl font-display text-lg font-bold text-white" style={{ background: d.team.colors.primary }}>{teams[d.team.team_id]?.short}</div>
              <div><div className="text-sm text-white">Coach {d.team.coach}</div><div className="text-[12px] text-slate-400">{d.team.formation} · {d.team.style}</div></div>
            </div>
            <div className="label mb-1 mt-5">Patterns this match</div>
            {d.patterns?.filter((p: any) => p.event === "start").map((p: any, i: number) => <div key={i} className="text-[12px] text-slate-300"><span className="font-mono text-slate-500">{p.minute}'</span> {p.type.replaceAll("_", " ").toLowerCase()}</div>)}
            <div className="label mb-1 mt-5">Historical archive</div>
            {d.history?.map((m: any) => <div key={m.doc_id} className="mb-1 rounded bg-white/[0.03] px-2 py-1 text-[12px]"><span className="text-white">{m.title}</span></div>)}
            <div className="label mb-1 mt-5">Memories</div>
            {d.memories?.map((m: any) => <div key={m.memory_id} className="mb-1 text-[12px] text-slate-400">• {m.text}</div>)}
          </div>
        </Panel>
      ))}
      <Panel title="Head to head · this match" className="order-2">
        <div className="h-full overflow-y-auto p-5">
          {rows.map(([k, label, fmt, inv]) => (
            <VersusBar key={k} label={label} home={h.match?.[k]} away={a.match?.[k]} homeColor={hc} awayColor={ac} fmt={fmt} invert={inv} />
          ))}
        </div>
      </Panel>
    </div>
  );
}
