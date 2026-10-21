import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { Panel, Sparkline, VersusBar, pct } from "../components/ui";

export function MiniPitch({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <svg viewBox="-2 -2 109 72" className={className}>
      <rect x={0} y={0} width={105} height={68} rx={1} fill="#0f3d24" stroke="rgba(255,255,255,.5)" strokeWidth={0.3} />
      {Array.from({ length: 9 }).map((_, i) => <rect key={i} x={i * 11.67} y={0} width={5.83} height={68} fill="rgba(255,255,255,.025)" />)}
      <line x1={52.5} x2={52.5} y1={0} y2={68} stroke="rgba(255,255,255,.5)" strokeWidth={0.3} />
      <circle cx={52.5} cy={34} r={9.15} fill="none" stroke="rgba(255,255,255,.5)" strokeWidth={0.3} />
      <rect x={0} y={13.84} width={16.5} height={40.32} fill="none" stroke="rgba(255,255,255,.5)" strokeWidth={0.3} />
      <rect x={88.5} y={13.84} width={16.5} height={40.32} fill="none" stroke="rgba(255,255,255,.5)" strokeWidth={0.3} />
      {children}
    </svg>
  );
}

export default function TacticsScreen() {
  const { matchId, teams, roster, clock, homeId: H, awayId: A } = useStore();
  const [t, setT] = useState<any>(null);
  const [team, setTeam] = useState(H);
  useEffect(() => { setTeam(H); }, [H]);
  useEffect(() => {
    const load = () => api.tactics(matchId).then(setT).catch(() => {});
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [matchId]);
  if (!t) return <div className="grid h-full place-items-center text-slate-500">Loading tactics…</div>;
  const h = teams[H]?.colors.primary ?? "#3BA4F6", a = teams[A]?.colors.primary ?? "#F2555A";
  if (!t.totals[H] || !t.totals[A]) return <div className="grid h-full place-items-center text-slate-500">Loading tactics…</div>;
  const color = teams[team]?.colors.primary;
  const net = t.networks[team] ?? [];
  const max = Math.max(1, ...net.map((n: any) => n.count));
  const pos = t.avg_positions ?? {};
  const players = Object.keys(pos).filter((p) => roster[p]?.team_id === team);
  const degree: Record<string, number> = {};
  net.forEach((n: any) => { degree[n.from] = (degree[n.from] ?? 0) + n.count; degree[n.to] = (degree[n.to] ?? 0) + n.count; });
  const T = t.totals, W5 = t.window;
  return (
    <div className="grid h-full grid-cols-[1.35fr_1fr] grid-rows-[auto_1fr] gap-3 overflow-hidden p-3">
      <Panel title={`Passing network & average positions · ${clock}`} className="row-span-2"
             right={<div className="flex gap-1">{Object.entries(teams).map(([id, tm]) => (
               <button key={id} onClick={() => setTeam(id)} className={`chip ${team === id ? "border-white/30" : ""}`} style={{ color: tm.colors.primary }}>{tm.short}</button>))}</div>}>
        <div className="flex h-full flex-col p-4">
          <MiniPitch className="w-full">
            {net.map((n: any, i: number) => {
              const p1 = pos[n.from], p2 = pos[n.to];
              if (!p1 || !p2) return null;
              return <line key={i} x1={p1[0]} y1={p1[1]} x2={p2[0]} y2={p2[1]} stroke={color} strokeOpacity={0.25 + (0.7 * n.count) / max} strokeWidth={0.25 + (1.4 * n.count) / max} strokeLinecap="round" />;
            })}
            {players.map((p) => (
              <g key={p}>
                <circle cx={pos[p][0]} cy={pos[p][1]} r={1.6 + Math.min(2.2, (degree[p] ?? 0) / 25)} fill={color} stroke="white" strokeWidth={0.3} />
                <text x={pos[p][0]} y={pos[p][1] + 0.9} fontSize={2.2} textAnchor="middle" fill="white" fontWeight={700}>{roster[p]?.number}</text>
                <text x={pos[p][0]} y={pos[p][1] + 5.2} fontSize={1.7} textAnchor="middle" fill="rgba(255,255,255,.75)">{roster[p]?.name.split(" ").pop()}</text>
              </g>
            ))}
          </MiniPitch>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {net.slice(0, 6).map((n: any, i: number) => (
              <div key={i} className="rounded-lg bg-white/[0.03] px-2.5 py-1.5 text-[12px]">
                <span className="text-white">{roster[n.from]?.name.split(" ").pop()}</span> → <span className="text-white">{roster[n.to]?.name.split(" ").pop()}</span>
                <span className="float-right font-mono" style={{ color }}>{n.count}</span>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <div className="label mb-1">Momentum (home ↑ / away ↓)</div>
            <Sparkline data={(t.momentum_series ?? []).map((m: any) => m.m)} height={56} home={h} away={a} />
          </div>
        </div>
      </Panel>
      <Panel title="Team metrics · match / last 5 min">
        <div className="grid grid-cols-2 gap-x-6 p-4">
          <div>
            <div className="label mb-1">Full match</div>
            <VersusBar label="Possession" home={T[H].possession} away={T[A].possession} homeColor={h} awayColor={a} fmt={pct} />
            <VersusBar label="xG" home={T[H].xg} away={T[A].xg} homeColor={h} awayColor={a} />
            <VersusBar label="Field tilt" home={T[H].field_tilt} away={T[A].field_tilt} homeColor={h} awayColor={a} fmt={pct} />
            <VersusBar label="PPDA (lower = more press)" home={T[H].ppda} away={T[A].ppda} homeColor={h} awayColor={a} invert />
            <VersusBar label="Progressive passes" home={T[H].progressive_passes} away={T[A].progressive_passes} homeColor={h} awayColor={a} />
            <VersusBar label="High turnovers" home={T[H].high_turnovers} away={T[A].high_turnovers} homeColor={h} awayColor={a} />
            <VersusBar label="Def. line height (m)" home={T[H].defensive_line_height} away={T[A].defensive_line_height} homeColor={h} awayColor={a} />
          </div>
          <div>
            <div className="label mb-1">Last 5 minutes</div>
            <VersusBar label="Possession" home={W5[H].possession} away={W5[A].possession} homeColor={h} awayColor={a} fmt={pct} />
            <VersusBar label="xG" home={W5[H].xg} away={W5[A].xg} homeColor={h} awayColor={a} />
            <VersusBar label="Field tilt" home={W5[H].field_tilt} away={W5[A].field_tilt} homeColor={h} awayColor={a} fmt={pct} />
            <VersusBar label="PPDA" home={W5[H].ppda} away={W5[A].ppda} homeColor={h} awayColor={a} invert />
            <VersusBar label="Pressures" home={W5[H].pressures} away={W5[A].pressures} homeColor={h} awayColor={a} />
            <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
              {Object.entries(t.formations).map(([id, f]: any) => (
                <div key={id} className="rounded-lg bg-white/[0.03] p-2">
                  <div style={{ color: teams[id]?.colors.primary }} className="font-semibold">{teams[id]?.short}</div>
                  <div className="text-slate-400">nominal <span className="font-mono text-white">{f.nominal}</span></div>
                  <div className="text-slate-400">live shape <span className="font-mono text-cyan-200">{f.live}</span></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Panel>
      <Panel title="Detected patterns & predictions">
        <div className="h-full space-y-2 overflow-y-auto p-4">
          {t.active_patterns.map((p: any) => (
            <div key={p.type + p.team_id} className="rounded-lg border p-2.5" style={{ borderColor: `${teams[p.team_id]?.colors.primary}55` }}>
              <div className="flex justify-between text-[12px]"><span className="font-semibold text-white">{p.type.replaceAll("_", " ")}</span><span className="font-mono text-slate-400">{pct(p.confidence)} · since {p.started_minute}'</span></div>
              <div className="mt-1 text-[12px] text-slate-300">{p.summary}</div>
            </div>
          ))}
          {!t.active_patterns.length && <div className="text-[12px] text-slate-500">No active patterns right now.</div>}
          <div className="label pt-2">Predictions — probabilistic, not facts</div>
          {t.predictions.map((p: any) => (
            <div key={p.label}>
              <div className="flex justify-between text-[12px]"><span>{p.label}</span><span className="font-mono text-amber-300">{pct(p.probability)}</span></div>
              <div className="h-1 rounded bg-white/5"><div className="h-full rounded bg-gradient-to-r from-amber-500 to-yellow-300" style={{ width: pct(p.probability) }} /></div>
              <div className="text-[10.5px] text-slate-500">{p.basis}</div>
            </div>
          ))}
          <div className="label pt-2">Pattern history</div>
          {t.pattern_history.slice(-10).reverse().map((p: any, i: number) => (
            <div key={i} className="text-[12px] text-slate-400"><span className="font-mono text-slate-500">{p.minute}'</span> {p.event === "start" ? "▲" : "▼"} <span style={{ color: teams[p.team_id]?.colors.primary }}>{teams[p.team_id]?.short}</span> {p.type.replaceAll("_", " ").toLowerCase()}</div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
