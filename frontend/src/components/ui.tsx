import clsx from "clsx";
import type { ReactNode } from "react";

export const CATEGORY: Record<string, { label: string; color: string }> = {
  GOAL: { label: "Goal", color: "#FDE047" },
  TURNING_POINT: { label: "Turning point", color: "#F97316" },
  TACTICAL_SHIFT: { label: "Tactical shift", color: "#22D3EE" },
  HIGH_PRESS: { label: "High press", color: "#FACC15" },
  DANGEROUS_ATTACK: { label: "Dangerous attack", color: "#F87171" },
  PLAYER_IMPACT: { label: "Player impact", color: "#A78BFA" },
  MOMENTUM_SHIFT: { label: "Momentum shift", color: "#34D399" },
  ANSWER: { label: "Answer", color: "#7CC4FF" },
  ROUTINE: { label: "Moment", color: "#94A3B8" },
};

export const cat = (c: string) => CATEGORY[c] ?? { label: c.replaceAll("_", " ").toLowerCase(), color: "#94A3B8" };

export function Badge({ category }: { category: string }) {
  const c = cat(category);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          style={{ color: c.color, background: `${c.color}1f`, boxShadow: `inset 0 0 0 1px ${c.color}44` }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c.color }} />
      {c.label}
    </span>
  );
}

export function Panel({ title, right, children, className }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={clsx("glass flex min-h-0 flex-col", className)}>
      {title && (
        <header className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
          <div className="label">{title}</div>
          {right}
        </header>
      )}
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function Confidence({ value, size = 34 }: { value: number; size?: number }) {
  const r = size / 2 - 3;
  const c = 2 * Math.PI * r;
  const color = value >= 0.8 ? "#34D399" : value >= 0.6 ? "#FACC15" : "#F87171";
  return (
    <div className="relative" style={{ width: size, height: size }} title={`Confidence ${Math.round(value * 100)}%`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,.08)" strokeWidth={3} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={3} fill="none" strokeDasharray={c} strokeDashoffset={c * (1 - value)} strokeLinecap="round" />
      </svg>
      <span className="absolute inset-0 grid place-items-center font-mono text-[10px] text-slate-200">{Math.round(value * 100)}</span>
    </div>
  );
}

export function Stat({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className="label">{label}</div>
      <div className="mt-1 font-display text-xl font-semibold" style={{ color: accent }}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-400">{sub}</div>}
    </div>
  );
}

/** Two-sided comparison bar (home left, away right). */
export function VersusBar({ label, home, away, homeColor, awayColor, fmt = (v: number) => String(v), invert }: {
  label: string; home: number | null; away: number | null; homeColor: string; awayColor: string; fmt?: (v: number) => string; invert?: boolean;
}) {
  const h = home ?? 0, a = away ?? 0;
  const total = h + a || 1;
  let hp = (h / total) * 100;
  if (invert) hp = 100 - hp;
  return (
    <div className="py-1.5">
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-mono text-slate-200">{home == null ? "–" : fmt(h)}</span>
        <span className="text-slate-400">{label}</span>
        <span className="font-mono text-slate-200">{away == null ? "–" : fmt(a)}</span>
      </div>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-white/5">
        <div style={{ width: `${hp}%`, background: homeColor }} className="transition-all duration-700" />
        <div style={{ width: `${100 - hp}%`, background: awayColor }} className="transition-all duration-700" />
      </div>
    </div>
  );
}

export function Sparkline({ data, height = 40, home = "#3BA4F6", away = "#F2555A" }: { data: number[]; height?: number; home?: string; away?: string }) {
  const w = 300;
  if (data.length < 2) return <div style={{ height }} />;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * w, height / 2 - v * (height / 2 - 2)]);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
  const area = `${path}L${w},${height / 2}L0,${height / 2}Z`;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }}>
      <defs>
        <clipPath id="top"><rect x="0" y="0" width={w} height={height / 2} /></clipPath>
        <clipPath id="bottom"><rect x="0" y={height / 2} width={w} height={height / 2} /></clipPath>
      </defs>
      <path d={area} fill={home} opacity={0.35} clipPath="url(#top)" />
      <path d={area} fill={away} opacity={0.35} clipPath="url(#bottom)" />
      <path d={path} fill="none" stroke="white" strokeOpacity={0.7} strokeWidth={1.2} />
      <line x1={0} x2={w} y1={height / 2} y2={height / 2} stroke="white" strokeOpacity={0.12} />
    </svg>
  );
}

export const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);
