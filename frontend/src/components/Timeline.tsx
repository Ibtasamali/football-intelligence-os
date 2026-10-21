import { useStore } from "../lib/store";
import { replayInsight } from "../lib/replay";
import { cat } from "./ui";

const KEY = new Set(["GOAL", "TURNING_POINT", "TACTICAL_SHIFT", "HIGH_PRESS", "DANGEROUS_ATTACK", "MOMENTUM_SHIFT", "PLAYER_IMPACT"]);

export default function Timeline() {
  const insights = useStore((s) => s.insights.filter((i) => KEY.has(i.category) && (i.significance >= 0.55 || i.category === "GOAL")));
  const series = useStore((s) => s.momentumSeries);
  const clock = useStore((s) => s.clock);
  const featured = useStore((s) => s.featuredId);
  const teams = useStore((s) => s.teams);
  const homeId = useStore((s) => s.homeId);
  const awayId = useStore((s) => s.awayId);
  const duration = useStore((s) => s.match?.duration_minutes ?? 90);
  const now = Number(clock.split(":")[0]) + Number(clock.split(":")[1]) / 60;
  const maxM = duration + 4;
  const w = 1000, h = 46;
  const pts = series.map((v, i) => [(i / Math.max(1, series.length - 1)) * (now / maxM) * w, h / 2 - v * (h / 2 - 3)]);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  return (
    <div className="glass relative px-4 pb-3 pt-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="label">AI timeline · momentum</span>
        <span className="text-[10px] text-slate-500">click a marker to replay it in 3D</span>
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-12 w-full">
          <rect x={0} y={0} width={(now / maxM) * w} height={h} fill="rgba(255,255,255,0.02)" />
          <line x1={0} x2={w} y1={h / 2} y2={h / 2} stroke="white" strokeOpacity={0.1} />
          <line x1={(45 / maxM) * w} x2={(45 / maxM) * w} y1={0} y2={h} stroke="white" strokeOpacity={0.15} strokeDasharray="3 3" />
          {path && <path d={`${path}L${pts[pts.length - 1][0]},${h / 2}L0,${h / 2}Z`} fill="url(#mg)" opacity={0.55} />}
          {path && <path d={path} fill="none" stroke="white" strokeOpacity={0.6} strokeWidth={1} />}
          <defs>
            <linearGradient id="mg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={teams[homeId]?.colors.primary ?? "#3BA4F6"} />
              <stop offset="50%" stopColor="transparent" />
              <stop offset="100%" stopColor={teams[awayId]?.colors.primary ?? "#F2555A"} />
            </linearGradient>
          </defs>
        </svg>
        {insights.map((i) => {
          const left = ((i.minute + i.second / 60) / maxM) * 100;
          const c = cat(i.category);
          return (
            <button key={i.insight_id} onClick={() => replayInsight(i)} title={`${i.minute}' ${i.headline}`}
                    className="group absolute top-[17px] -translate-x-1/2" style={{ left: `${left}%` }}>
              <span className={`block rounded-full border-2 border-ink-950 transition group-hover:scale-150 ${i.category === "GOAL" ? "h-4 w-4" : "h-3 w-3"} ${featured === i.insight_id ? "ring-2 ring-white" : ""}`}
                    style={{ background: c.color, boxShadow: `0 0 12px ${c.color}` }} />
              <span className="pointer-events-none absolute left-1/2 top-5 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-ink-800 px-2 py-1 text-[11px] text-white shadow-xl group-hover:block">
                {i.minute}' · {i.headline}
              </span>
            </button>
          );
        })}
        <div className="absolute top-0 h-12 w-px bg-cyan-300 shadow-[0_0_10px_#22d3ee]" style={{ left: `${(now / maxM) * 100}%` }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
        {Array.from({ length: Math.floor(duration / 15) + 1 }, (_, i) => i * 15).map((m) => <span key={m}>{m}'</span>)}
      </div>
    </div>
  );
}
