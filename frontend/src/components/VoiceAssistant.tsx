import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AudioLines, Loader2, Mic, MicOff, Send, Sparkles, Square, X } from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { createRecognizer, onSpeaking, quickSay, speak, stopSpeaking } from "../lib/voice";
import { replayInsight } from "../lib/replay";
import type { Insight } from "../lib/types";
import { Badge, Confidence } from "./ui";
import { langMeta } from "../lib/i18n";

const PERSONAS = [
  { id: "casual_commentator", label: "Commentator" }, { id: "tactical_analyst", label: "Tactical analyst" },
  { id: "coach", label: "Coach" }, { id: "kids", label: "Kids mode" }, { id: "expert_analyst", label: "Expert" },
];
const SUGGESTIONS = ["What just happened?", "Why did that goal happen?", "Explain this like I'm a beginner",
  "Give me an analyst-level explanation", "Compare this with a historical match", "Who is the best player?", "What is likely to happen next?"];

interface Turn { q: string; a?: Insight; error?: string; latency?: number }

export default function VoiceAssistant() {
  const { voiceOpen, set, matchId, profile } = useStore();
  const [persona, setPersona] = useState(profile.persona);
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeakingState] = useState(false);
  const rec = useRef<any>(null);
  const [live, setLive] = useState(false);
  const liveRef = useRef(false);
  const [phase, setPhase] = useState<"idle" | "listening" | "thinking" | "speaking">("idle");
  const copilotQuestion = useStore((s) => s.copilotQuestion);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => { const off = onSpeaking(setSpeakingState); return () => { off(); }; }, []);
  useEffect(() => { setPersona(profile.persona); }, [profile.persona]);
  // braces matter: newer Chrome returns a Promise from scrollTo(), which React would treat as a cleanup
  useEffect(() => { void scroller.current?.scrollTo({ top: 1e9, behavior: "smooth" }); }, [turns]);

  const ask = async (q: string, awaitSpeech = false): Promise<void> => {
    if (!q.trim() || busy) return;
    setText("");
    setBusy(true);
    setTurns((t) => [...t, { q }]);
    const t0 = performance.now();
    try {
      const lang = profile.language || "en";
      const r = await api.ask(matchId, q, profile.user_id, persona, undefined, lang);
      const a: Insight = r.answer;
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, a, latency: performance.now() - t0 } : x)));
      useStore.getState().set({ copilotShownAt: Date.now() });
      if (a.visualization?.some((c) => c.type === "highlight_zone" || c.type === "highlight_players")) useStore.getState().focusInsight(a);
      const loc = (a as any).localized;
      setBusy(false);
      setPhase("speaking");
      const spoken = loc && loc.language !== "en"
        ? speak(loc.voice || loc.explanation || loc.headline, persona, loc.language, langMeta(loc.language)?.locale)
        : speak(a.voice_scripts?.[persona] || a.statistics?.answer || a.headline, persona);
      const done = spoken.then(() => { setPhase("idle"); useStore.getState().set({ copilotAnsweredAt: Date.now() }); });
      if (awaitSpeech) await done;
    } catch (e: any) {
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error: String(e.message ?? e) } : x)));
      setPhase("idle");
      useStore.getState().set({ copilotAnsweredAt: Date.now() });
    } finally {
      setBusy(false);
    }
  };

  // ---- Auto Demo hook: questions pushed through the store are asked like a fan would
  useEffect(() => {
    if (!copilotQuestion) return;
    useStore.getState().set({ copilotQuestion: null, voiceOpen: true });
    setPhase("thinking");
    ask(copilotQuestion);
  }, [copilotQuestion]);

  // ---- Live conversation: listen → think → speak → listen …
  const ACKS = ["Let me check the match data.", "Good question, one second.", "Looking at the evidence now."];
  const listenOnce = () => {
    if (!liveRef.current) return;
    const locale = langMeta(profile.language || "en")?.locale ?? "en-US";
    const r = createRecognizer(locale);
    if (!r) { setText("Live conversation needs Chrome or Edge."); stopLive(); return; }
    rec.current = r;
    let finalText = "";
    r.onresult = (e: any) => {
      const res = Array.from(e.results as ArrayLike<any>).map((x: any) => x[0].transcript).join("");
      setText(res);
      if (e.results[e.results.length - 1].isFinal) finalText = res;
    };
    r.onerror = () => {};
    r.onend = async () => {
      setListening(false);
      if (!liveRef.current) return;
      if (!finalText.trim()) { setTimeout(listenOnce, 250); return; }   // silence → keep listening
      setPhase("thinking");
      if ((profile.language || "en") === "en") quickSay(ACKS[Math.floor(Math.random() * ACKS.length)], locale);
      await ask(finalText, true);
      if (liveRef.current) setTimeout(listenOnce, 300);
    };
    setListening(true);
    setPhase("listening");
    r.start();
  };
  const startLive = () => {
    liveRef.current = true;
    setLive(true);
    stopSpeaking();
    listenOnce();
  };
  const stopLive = () => {
    liveRef.current = false;
    setLive(false);
    rec.current?.stop?.();
    setListening(false);
    setPhase("idle");
  };
  // Space bar interrupts the answer and hands the turn back to the fan
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space" && liveRef.current && phase === "speaking" && !(e.target instanceof HTMLInputElement)) {
        e.preventDefault();
        stopSpeaking();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase]);

  const toggleMic = () => {
    if (listening) { rec.current?.stop(); return; }
    const r = createRecognizer(langMeta(profile.language || "en")?.locale ?? "en-US");
    if (!r) { setText("Voice input needs Chrome/Edge — type your question instead."); return; }
    rec.current = r;
    stopSpeaking();
    r.onresult = (e: any) => {
      const res = Array.from(e.results as ArrayLike<any>).map((x: any) => x[0].transcript).join("");
      setText(res);
      if (e.results[e.results.length - 1].isFinal) ask(res);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    setListening(true);
    r.start();
  };

  return (
    <>
      <motion.button whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.95 }} onClick={() => set({ voiceOpen: !voiceOpen })}
        className="fixed bottom-5 right-5 z-50 grid h-16 w-16 place-items-center rounded-full bg-gradient-to-br from-cyan-300 via-sky-500 to-indigo-600 text-ink-950 shadow-[0_0_40px_rgba(34,211,238,.55)]">
        {(speaking || listening) && <span className="absolute inset-0 animate-ping rounded-full bg-cyan-300/40" />}
        <Sparkles size={26} />
      </motion.button>
      <AnimatePresence>
        {voiceOpen && (
          <motion.div initial={{ opacity: 0, y: 30, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 30 }}
            className="glass-strong fixed bottom-24 right-5 z-50 flex h-[min(620px,calc(100vh-120px))] w-[460px] flex-col overflow-hidden">
            <header className="border-b border-white/10 p-4">
              <div className="flex items-center gap-2">
                <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-cyan-300 to-indigo-500 text-ink-950"><Sparkles size={16} /></div>
                <div className="flex-1">
                  <div className="font-display text-sm font-semibold text-white">Match Copilot</div>
                  <div className="text-[11px] text-slate-400">Voice · Agentic RAG · CAG · MAG — remembers {profile.display_name}</div>
                </div>
                {speaking && <button className="btn" onClick={stopSpeaking}><Square size={12} /> Stop</button>}
                <button className="btn" onClick={() => set({ voiceOpen: false })}><X size={14} /></button>
              </div>
              <button onClick={live ? stopLive : startLive}
                      className={`mt-3 flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-[13px] font-semibold transition ${
                        live ? "bg-rose-500/90 text-white" : "bg-gradient-to-r from-cyan-400 to-indigo-500 text-ink-950 hover:brightness-110"}`}>
                <AudioLines size={16} />
                {live ? "End live conversation" : "Start live conversation (hands-free)"}
              </button>
              {live && (
                <div className="mt-2 flex items-center gap-2 rounded-lg bg-white/[0.04] px-3 py-2 text-[12px]">
                  <span className={`h-2.5 w-2.5 rounded-full ${phase === "listening" ? "animate-pulse bg-cyan-300" : phase === "thinking" ? "animate-pulse bg-amber-300" : phase === "speaking" ? "animate-pulse bg-violet-300" : "bg-slate-500"}`} />
                  <span className="text-slate-200">{phase === "listening" ? "Listening… just talk" : phase === "thinking" ? "Agents are checking the data…" : phase === "speaking" ? "Speaking — press Space or tap Stop to interrupt" : "Ready"}</span>
                  {phase === "speaking" && <button className="btn ml-auto" onClick={stopSpeaking}><Square size={11} /> Stop</button>}
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-1">
                {PERSONAS.map((p) => (
                  <button key={p.id} onClick={() => setPersona(p.id)}
                          className={`chip ${persona === p.id ? "border-cyan-300/60 bg-cyan-400/15 text-cyan-100" : "text-slate-300"}`}>{p.label}</button>
                ))}
              </div>
            </header>
            <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto p-4">
              {!turns.length && (
                <div className="space-y-2">
                  <div className="text-[12px] text-slate-400">Ask anything about the match — by voice or text.</div>
                  {SUGGESTIONS.map((s) => <button key={s} className="btn mr-1" onClick={() => ask(s)}>{s}</button>)}
                </div>
              )}
              {turns.map((t, i) => (
                <div key={i} className="space-y-2">
                  <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-cyan-400/15 px-3 py-2 text-[13px] text-cyan-50">{t.q}</div>
                  {!t.a && !t.error && <div className="flex items-center gap-2 text-[12px] text-slate-400"><Loader2 size={14} className="animate-spin" /> routing agents, checking context and memory…</div>}
                  {t.error && <div className="text-[12px] text-red-300">{t.error}</div>}
                  {t.a && (
                    <div className="rounded-2xl rounded-bl-sm border border-white/10 bg-white/[0.03] p-3">
                      <div className="mb-1 flex items-center gap-2"><Badge category="ANSWER" />
                        <span className="text-[10px] text-slate-500">{t.a.statistics?.intent} · {Math.round(t.latency ?? 0)}ms{t.a.provenance.cache_hit ? " · reused, 0 tokens" : ""}</span>
                        <div className="ml-auto"><Confidence value={t.a.provenance.confidence} size={26} /></div>
                      </div>
                      {(() => {
                        const loc = (t.a as any).localized;
                        const tr = loc && loc.language !== "en" ? loc : null;
                        const dir = tr && langMeta(tr.language)?.rtl ? "rtl" : undefined;
                        return (<>
                          <div dir={dir} className="font-display text-[14px] font-semibold text-white">{tr?.headline || t.a.headline}</div>
                          <div dir={dir} className="mt-1 text-[13px] leading-relaxed text-slate-300">{tr?.explanation || t.a.statistics?.answer}</div>
                          {tr && <div className="mt-1 text-[10px] text-slate-500">🌐 answered in {langMeta(tr.language)?.native} · understood as "{t.a.statistics?.question_english}"</div>}
                        </>);
                      })()}
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <button className="btn" onClick={() => set({ whyId: t.a!.insight_id })}>Why?</button>
                        {t.a.visualization?.length > 0 && <button className="btn" onClick={() => replayInsight(t.a!)}>Show in 3D</button>}
                        <button className="btn" onClick={() => {
                          const loc = (t.a as any).localized;
                          if (loc && loc.language !== "en") speak(loc.voice || loc.explanation, persona, loc.language, langMeta(loc.language)?.locale);
                          else speak(t.a!.voice_scripts?.[persona] || t.a!.statistics?.answer, persona);
                        }}>Listen</button>
                        <span className="chip text-[10px] text-slate-400">{t.a.provenance.graph_path?.length} graph steps · {t.a.provenance.model}</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <footer className="border-t border-white/10 p-3">
              <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); ask(text); }}>
                <button type="button" onClick={toggleMic}
                        className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${listening ? "bg-red-500 text-white" : "bg-white/10 text-cyan-200 hover:bg-white/15"}`}>
                  {listening ? <MicOff size={16} /> : <Mic size={16} />}
                </button>
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening…" : "Ask about the match…"}
                       className="h-10 flex-1 rounded-full border border-white/10 bg-black/30 px-4 text-[13px] text-white outline-none focus:border-cyan-300/50" />
                <button className="grid h-10 w-10 place-items-center rounded-full bg-cyan-400 text-ink-950" disabled={busy}>{busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}</button>
              </form>
            </footer>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
