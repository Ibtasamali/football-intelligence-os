import { useEffect, useState } from "react";
import { Accessibility, X } from "lucide-react";
import { useA11y, announce, applyClasses } from "../lib/a11y";
import { useStore } from "../lib/store";
import { api } from "../lib/api";

function Switch({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-lg p-2 hover:bg-white/5">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-4 w-4 accent-cyan-400" />
      <span><span className="block text-[13px] font-medium text-white">{label}</span><span className="block text-[11.5px] text-slate-400">{hint}</span></span>
    </label>
  );
}

export async function describeNow() {
  const s = useStore.getState();
  try {
    const r = await fetch(`/api/matches/${s.matchId}/describe`).then((x) => x.json());
    announce(r.text, { urgent: true });
  } catch { /* ignore */ }
}

/** Top-bar button + settings panel + screen-reader live region + keyboard shortcuts. */
export default function A11yPanel() {
  const a = useA11y();
  const [open, setOpen] = useState(false);
  useEffect(() => { applyClasses(); }, []);
  useEffect(() => {
    const show = () => { setOpen(true); useA11y.getState().set({ enabled: true, audio: true, contrast: true }); };
    const hide = () => setOpen(false);
    window.addEventListener("fios:a11y-demo", show);
    window.addEventListener("fios:a11y-demo-close", hide);
    return () => { window.removeEventListener("fios:a11y-demo", show); window.removeEventListener("fios:a11y-demo-close", hide); };
  }, []);
  useEffect(() => {
    const onKey = async (e: KeyboardEvent) => {
      if (!useA11y.getState().enabled) return;
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      const s = useStore.getState();
      if (e.key === "d" || e.key === "D") { e.preventDefault(); describeNow(); }
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        const r = await api.replay(s.matchId, s.replay?.running ? "pause" : "start");
        s.set({ replay: r });
        announce(r.running ? "Match playing." : `Paused at ${r.clock}.`, { urgent: true });
      }
      if (e.key === "w" || e.key === "W") {
        const ins = s.insights.find((i) => i.insight_id === s.featuredId) ?? s.insights[s.insights.length - 1];
        if (ins) announce(`${ins.headline}. ${ins.explanations?.beginner || ins.commentary}`, { urgent: true });
      }
      if (e.key === "h" || e.key === "H") announce("Shortcuts: D describes the pitch. P plays or pauses. W explains the latest moment. H repeats this help.", { urgent: true });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <button className={`btn shrink-0 ${a.enabled ? "border-emerald-300/60 text-emerald-200" : ""}`} onClick={() => setOpen(!open)}
              aria-label="Accessibility settings" title="Accessibility">
        <Accessibility size={14} /> {a.enabled ? "A11y on" : ""}
      </button>
      {open && (
        <div className="glass-strong fixed right-4 top-[70px] z-[70] max-h-[calc(100%-90px)] w-[340px] overflow-y-auto p-4" role="dialog" aria-label="Accessibility settings">
          <div className="mb-2 flex items-center gap-2">
            <Accessibility size={16} className="text-emerald-300" />
            <div className="flex-1 font-display text-[15px] font-semibold text-white">Accessibility mode</div>
            <button className="btn" onClick={() => setOpen(false)} aria-label="Close"><X size={13} /></button>
          </div>
          <Switch label="Enable accessibility mode" hint="For blind and low-vision fans: audio description and keyboard control" value={a.enabled}
                  onChange={(v) => { a.set({ enabled: v }); if (v) setTimeout(() => announce("Accessibility mode on. Press D to describe the pitch, P to play or pause, H for help.", { urgent: true }), 50); }} />
          <div className={a.enabled ? "" : "pointer-events-none opacity-40"}>
            <Switch label="Live audio description" hint="Goals, shots, cards, substitutions and tactical changes are described out loud" value={a.audio} onChange={(v) => a.set({ audio: v })} />
            <Switch label="High contrast" hint="Brighter text and stronger outlines" value={a.contrast} onChange={(v) => a.set({ contrast: v })} />
            <Switch label="Large text" hint="Enlarges the whole interface" value={a.large} onChange={(v) => a.set({ large: v })} />
            <Switch label="Reduce motion" hint="Turns off non-essential animations" value={a.reducedMotion} onChange={(v) => a.set({ reducedMotion: v })} />
          </div>
          <div className="mt-2 rounded-lg bg-white/[0.04] p-2.5 text-[12px] text-slate-300">
            <b>Keyboard:</b> <kbd>D</kbd> describe the pitch · <kbd>P</kbd> play/pause · <kbd>W</kbd> explain latest moment · <kbd>H</kbd> help
          </div>
          <button className="btn-primary mt-3 w-full justify-center" onClick={describeNow} disabled={!a.enabled}>🔊 Describe the pitch now</button>
        </div>
      )}
      {/* screen-reader live region */}
      <div aria-live="polite" role="status" className="sr-only">{a.enabled ? a.lastAnnouncement : ""}</div>
    </>
  );
}
