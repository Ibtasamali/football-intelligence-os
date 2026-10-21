import { useEffect, useLayoutEffect, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { useStore, type Screen } from "../lib/store";

const STEPS: { target: string; screen?: Screen; title: string; text: string }[] = [
  { target: "kickoff", title: "1. Start the live match", text: "Press Kick off, or use Jump to… for an instant judging demo. The fast path updates the pitch in real time." },
  { target: "pipeline", screen: "pipeline", title: "2. See the evidence pipeline", text: "Open Pipeline to watch routing, specialist agents, RAG, verification and provenance for one moment." },
  { target: "coach", screen: "coach", title: "3. Generate the coach report", text: "The Microsoft Agent Framework desk turns verified match evidence into recommendations and a downloadable PDF." },
  { target: "traces", screen: "traces", title: "4. Inspect production telemetry", text: "Traces shows OpenTelemetry spans, latency and failures. Azure deployments export the same metadata to Application Insights." },
];

export default function JudgeTour() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const setStore = useStore((s) => s.set);
  const current = STEPS[step];
  const locate = () => setRect(document.querySelector(`[data-tour="${current.target}"]`)?.getBoundingClientRect() ?? null);
  useEffect(() => {
    const show = () => { setStep(0); setOpen(true); };
    window.addEventListener("fios:tour", show);
    const tour = new URLSearchParams(location.search).get("tour");
    if (tour !== "0" && (tour === "1" || !localStorage.getItem("fios-judge-tour-v1"))) setTimeout(show, 700);
    return () => window.removeEventListener("fios:tour", show);
  }, []);
  useLayoutEffect(() => {
    if (!open) return;
    if (current.screen) setStore({ screen: current.screen });
    const timer = setTimeout(locate, 80);
    window.addEventListener("resize", locate);
    return () => { clearTimeout(timer); window.removeEventListener("resize", locate); };
  }, [open, step]);
  const close = () => { localStorage.setItem("fios-judge-tour-v1", "done"); setOpen(false); };
  const next = () => step === STEPS.length - 1 ? close() : setStep(step + 1);
  if (!open) return null;
  const top = rect ? Math.min(window.innerHeight - 220, Math.max(76, rect.top)) : 100;
  const left = rect ? Math.min(window.innerWidth - 390, rect.right + 18) : 110;
  return <div className="fixed inset-0 z-[100] bg-black/55" role="dialog" aria-modal="true" aria-label="Judge tour">
    {rect && <div className="pointer-events-none fixed rounded-xl ring-4 ring-cyan-300 shadow-[0_0_45px_rgba(34,211,238,.6)]" style={{ top: rect.top - 5, left: rect.left - 5, width: rect.width + 10, height: rect.height + 10 }} />}
    <div className="glass-strong fixed w-[360px] p-5 shadow-2xl" style={{ top, left }}>
      <div className="flex items-start justify-between"><div className="label text-cyan-300">60-second judge tour · {step + 1}/{STEPS.length}</div><button onClick={close} aria-label="Close tour"><X size={16}/></button></div>
      <h2 className="mt-2 font-display text-xl font-bold text-white">{current.title}</h2>
      <p className="mt-2 text-[13px] leading-5 text-slate-300">{current.text}</p>
      <div className="mt-4 flex items-center justify-between"><div className="flex gap-1">{STEPS.map((_, i) => <span key={i} className={`h-1.5 w-6 rounded ${i === step ? "bg-cyan-300" : "bg-white/10"}`} />)}</div><button className="btn-primary" onClick={next}>{step === STEPS.length - 1 ? "Finish" : "Next"}<ArrowRight size={13}/></button></div>
    </div>
  </div>;
}
