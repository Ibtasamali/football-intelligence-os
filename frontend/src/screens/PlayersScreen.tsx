import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { MiniPitch } from "./TacticsScreen";
import { Panel, Stat } from "../components/ui";

export default function PlayersScreen() {
  const { matchId, roster, teams } = useStore();
  const [rank, setRank] = useState<any[]>([]);
  const [sel, setSel] = useState<string>("");
  const [detail, setDetail] = useState<any>(null);
  useEffect(() => {
    api.tactics(matchId).then((t) => { setRank(t.influence); setSel((s) => s && roster[s] ? s : t.influence[0]?.player_id ?? Object.keys(roster)[0]); }).catch(() => {});
  }, [matchId, roster]);
  useEffect(() => { if (sel) api.player(sel, matchId).then(setDetail).catch(() => setDetail(null)); }, [sel, matchId]);
  const p = roster[sel];
  const color = teams[p?.team_id ?? ""]?.colors.primary;
  const m = detail?.match;
  return (
    <div className="grid h-full grid-cols-[360px_1fr] gap-3 p-3">
      <Panel title="Influence ranking (live model)">
        <div className="h-full overflow-y-auto p-2">
          {rank.map((r, i) => (
            <button key={r.player_id} onClick={() => setSel(r.player_id)}
                    className={`flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition ${sel === r.player_id ? "bg-cyan-400/10" : "hover:bg-white/5"}`}>
              <span className="w-5 font-mono text-xs text-slate-500">{i + 1}</span>
              <span className="grid h-7 w-7 place-items-center rounded-full text-[11px] font-bold text-white" style={{ background: teams[r.team_id]?.colors.primary }}>{roster[r.player_id]?.number}</span>
              <span className="flex-1"><span className="block text-[13px] text-white">{r.name}</span><span className="text-[11px] text-slate-500">{r.position} · {teams[r.team_id]?.short}</span></span>
              <span className="font-mono text-sm text-cyan-200">{r.influence}</span>
            </button>
          ))}
          <div className="label mt-3 px-2">All players</div>
          {Object.values(roster).filter((r) => !rank.some((x) => x.player_id === r.player_id)).map((r) => (
            <button key={r.player_id} onClick={() => setSel(r.player_id)} className="block w-full rounded px-2 py-1 text-left text-[12px] text-slate-400 hover:bg-white/5">{r.number} · {r.name}{r.bench ? " (bench)" : ""}</button>
          ))}
        </div>
      </Panel>
      <div className="grid min-h-0 grid-cols-[1.2fr_1fr] gap-3">
        <Panel title="Player intelligence">
          {p && (
            <div className="h-full overflow-y-auto p-5">
              <div className="flex items-center gap-4">
                <div className="grid h-16 w-16 place-items-center rounded-2xl font-display text-2xl font-bold text-white" style={{ background: color, boxShadow: `0 0 40px ${color}66` }}>{p.number}</div>
                <div>
                  <div className="font-display text-2xl font-bold text-white">{p.name}</div>
                  <div className="text-sm text-slate-400">{p.position} · {teams[p.team_id]?.name}{p.role ? ` · ${p.role}` : ""}</div>
                </div>
                {m && <div className="ml-auto text-right"><div className="label">Influence rank</div><div className="font-display text-3xl font-bold text-cyan-200">#{m.influence_rank}</div></div>}
              </div>
              {m ? (
                <div className="mt-5 grid grid-cols-4 gap-2">
                  <Stat label="Goals" value={m.goals} /><Stat label="Assists" value={m.assists} />
                  <Stat label="xG" value={m.xg} /><Stat label="xA" value={m.xa} />
                  <Stat label="Progressive" value={m.progressive_actions} /><Stat label="Recoveries" value={m.recoveries} />
                  <Stat label="Pressures" value={m.pressures} /><Stat label="Passes done" value={m.passes_completed} />
                </div>
              ) : <div className="mt-6 text-sm text-slate-500">No match involvement yet.</div>}
              <div className="label mb-1 mt-5">Touch map</div>
              <MiniPitch className="w-full">
                {detail?.touch_map?.map(([x, y]: number[], i: number) => <circle key={i} cx={x} cy={y} r={1.3} fill={color} opacity={0.45} />)}
              </MiniPitch>
            </div>
          )}
        </Panel>
        <div className="flex min-h-0 flex-col gap-3">
          <Panel title="Key connections" className="flex-1">
            <div className="space-y-1.5 overflow-y-auto p-4">
              {detail?.connections?.map((c: any, i: number) => (
                <div key={i} className="flex justify-between rounded-lg bg-white/[0.03] px-3 py-1.5 text-[12px]">
                  <span>{roster[c.from]?.name} → {roster[c.to]?.name}</span><span className="font-mono text-cyan-200">{c.count}</span>
                </div>))}
            </div>
          </Panel>
          <Panel title="AI insights involving this player" className="flex-1">
            <div className="space-y-1.5 overflow-y-auto p-4 text-[12px]">
              {detail?.recent_insights?.map((r: any) => <div key={r.insight_id}><span className="font-mono text-slate-500">{r.minute}'</span> <span className="text-white">{r.headline}</span></div>)}
              {!detail?.recent_insights?.length && <div className="text-slate-500">None yet.</div>}
            </div>
          </Panel>
          <Panel title="Long-term memory (MAG)" className="flex-1">
            <div className="space-y-1.5 overflow-y-auto p-4 text-[12px] text-slate-300">
              {detail?.memories?.map((mm: any) => <div key={mm.memory_id}>• {mm.text}</div>)}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
