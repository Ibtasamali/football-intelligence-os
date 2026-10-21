import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BadgeCheck, Bell, Clapperboard, Copy, Download, Loader2, Mail, Mic2, Share2, Sparkles } from "lucide-react";
import { useStore } from "../lib/store";
import { take } from "../lib/prefetch";
import { type Lang, langMeta, loadLanguages } from "../lib/i18n";

export async function fetchRecap(matchId: string, language: string) {
  // text first (audio: false); the two-voice podcast is synthesised afterwards so the formats appear immediately
  const r = await fetch(`/api/matches/${matchId}/recap`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ language, audio: false }) });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(r.status === 409 ? "Start the match first — the recap is written from what has happened so far." : body.detail || `Request failed (${r.status})`);
  }
  return r.json();
}

function CopyBtn({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button className="btn" onClick={() => { navigator.clipboard?.writeText(text).then(() => { setOk(true); setTimeout(() => setOk(false), 1500); }); }}>
      <Copy size={12} /> {ok ? "Copied" : "Copy"}
    </button>
  );
}

function Card({ icon, title, children, right }: { icon: React.ReactNode; title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass p-4">
      <div className="mb-2 flex items-center gap-2 text-cyan-300">{icon}<span className="label text-cyan-300">{title}</span><div className="ml-auto">{right}</div></div>
      {children}
    </motion.div>
  );
}

let handled = 0;  // each auto-demo request runs once (StrictMode re-runs effects; remounts keep old requests)

export default function RecapScreen() {
  const { matchId, teams, homeId, awayId, profile } = useStore();
  const started = useStore((s) => (s.replay?.index ?? 0) > 0);
  const [langs, setLangs] = useState<Lang[]>([]);
  const [lang, setLang] = useState(profile.language || "en");
  const [recap, setRecap] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const studioRequest = useStore((s) => s.studioRequest);
  const setStore = useStore((s) => s.set);
  useEffect(() => { loadLanguages().then(setLangs).catch(() => {}); }, []);
  const gen = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await take(`recap:${matchId}:${lang}`, () => fetchRecap(matchId, lang));
      setRecap(r);
      setStore({ studioReadyAt: Date.now() });
      if (r.podcast_pending) {
        fetch(`/api/matches/${matchId}/recap/podcast`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ podcast: r.podcast, language: r.language }) })
          .then((x) => x.json()).then((p) => setRecap((cur: any) => cur === r ? { ...r, podcast_url: p.podcast_url, podcast_pending: false } : cur)).catch(() => {});
      }
    } catch (e: any) { setErr(String(e.message ?? e).slice(0, 200)); } finally { setBusy(false); }
  };
  useEffect(() => { if (studioRequest > handled && started && !busy) { handled = studioRequest; gen(); } }, [studioRequest]);
  const dir = langMeta(recap?.language ?? "en")?.rtl ? "rtl" : undefined;
  const h = teams[homeId], a = teams[awayId];
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(recap, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `recap-${matchId}-${recap.language}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1">
            <div className="label text-cyan-300">Recap Studio · for studios, broadcasters and streaming platforms</div>
            <h1 className="mt-1 font-display text-3xl font-bold text-white">One click, every format, verified</h1>
            <div className="mt-1 text-sm text-slate-400">Social post · push notification · broadcast lower-third · newsletter · two-host podcast, in 14 languages</div>
          </div>
          <select className="btn bg-ink-900" value={lang} onChange={(e) => setLang(e.target.value)}>
            {langs.map((l) => <option key={l.code} value={l.code}>🌐 {l.native}</option>)}
          </select>
          <button className="btn-primary" onClick={gen} disabled={busy || !started} title={started ? "" : "Start the match first"}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {recap ? "Regenerate" : "Generate recap"}</button>
          {recap && <button className="btn" onClick={exportJson}><Download size={13} /> Export JSON</button>}
        </div>
        {err && <div className="mt-4 rounded-lg bg-rose-500/10 p-3 text-[13px] text-rose-200">{err}</div>}
        {!recap && !busy && (
          <div className="glass mt-8 grid place-items-center p-14 text-center text-slate-400">
            Generates broadcaster-ready content from the verified match facts. Works mid-match (as a live update) or at full time.
          </div>
        )}
        {busy && <div className="glass mt-8 grid place-items-center p-14 text-slate-400"><Loader2 className="animate-spin" /> Writing, verifying and voicing every format…</div>}
        {recap && !busy && (
          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            {/* lower third */}
            <Card icon={<Clapperboard size={15} />} title="Broadcast lower-third" right={<CopyBtn text={`${recap.lower_third?.title}\n${recap.lower_third?.subtitle}`} />}>
              <div className="relative overflow-hidden rounded-lg bg-gradient-to-br from-slate-800 to-slate-900 p-6">
                <div className="absolute inset-0 opacity-30" style={{ background: `linear-gradient(90deg, ${h?.colors.primary}55, transparent 60%, ${a?.colors.primary}55)` }} />
                <div className="relative mt-10 flex items-stretch overflow-hidden rounded-md shadow-2xl" dir={dir}>
                  <div className="grid place-items-center px-3 font-display text-lg font-bold text-white" style={{ background: h?.colors.primary }}>{h?.short}</div>
                  <div className="flex-1 bg-white px-4 py-2">
                    <div className="font-display text-[17px] font-bold uppercase tracking-wide text-slate-900">{recap.lower_third?.title}</div>
                    <div className="text-[13px] text-slate-600">{recap.lower_third?.subtitle}</div>
                  </div>
                  <div className="grid place-items-center px-3 font-display text-lg font-bold text-white" style={{ background: a?.colors.primary }}>{a?.short}</div>
                </div>
              </div>
            </Card>
            {/* social + push */}
            <div className="grid gap-3">
              <Card icon={<Share2 size={15} />} title="Social post" right={<CopyBtn text={recap.social_post} />}>
                <div dir={dir} className="text-[14px] leading-relaxed text-slate-100">{recap.social_post}</div>
                <div className="mt-1 text-[11px] text-slate-500">{recap.social_post?.length} characters</div>
              </Card>
              <Card icon={<Bell size={15} />} title="Push notification" right={<CopyBtn text={recap.push_notification} />}>
                <div className="flex items-start gap-3 rounded-2xl bg-white/[0.06] p-3">
                  <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-sky-600 text-[10px] font-bold text-ink-950">FIOS</div>
                  <div dir={dir}><div className="text-[12px] font-semibold text-white">{recap.headline}</div><div className="text-[12.5px] text-slate-300">{recap.push_notification}</div></div>
                </div>
              </Card>
            </div>
            {/* podcast */}
            <Card icon={<Mic2 size={15} />} title="Two-host podcast (Azure neural voices)">
              {recap.podcast_url ? <audio controls src={recap.podcast_url} className="mb-3 w-full" />
                : <div className="mb-2 flex items-center gap-2 text-[12px] text-slate-400">{recap.podcast_pending ? <><Loader2 size={12} className="animate-spin" /> Voicing the podcast with two Azure neural voices…</> : "Audio needs Azure AI Speech."}</div>}
              <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1" dir={dir}>
                {recap.podcast?.map((l: any, i: number) => (
                  <div key={i} className="flex gap-2 text-[13px]">
                    <span className={`shrink-0 rounded px-1.5 font-mono text-[10px] font-bold ${l.host === "A" ? "bg-cyan-400/20 text-cyan-200" : "bg-fuchsia-400/20 text-fuchsia-200"}`}>{l.host === "A" ? "HOST" : "ANALYST"}</span>
                    <span className="text-slate-200">{l.line}</span>
                  </div>
                ))}
              </div>
            </Card>
            {/* newsletter + stats */}
            <Card icon={<Mail size={15} />} title="Newsletter" right={<CopyBtn text={recap.newsletter} />}>
              <div dir={dir} className="whitespace-pre-line text-[13.5px] leading-relaxed text-slate-200">{recap.newsletter}</div>
              <div className="mt-3 grid grid-cols-4 gap-1.5 text-center">
                {recap.key_stats?.map((s: any) => (
                  <div key={s.label} className="rounded-lg bg-white/[0.04] p-2">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">{s.label}</div>
                    <div className="font-mono text-[12px] text-white">{String(Object.values(s).slice(1).join(" – "))}</div>
                  </div>
                ))}
              </div>
            </Card>
            <div className="lg:col-span-2 flex flex-wrap items-center gap-2 text-[12px]">
              <span className={`chip ${recap.verification?.passed ? "text-emerald-300" : "text-amber-300"}`}><BadgeCheck size={12} />
                {recap.verification?.passed ? "All formats verified against the match facts" : `Corrected: ${recap.verification?.corrected_fields?.join(", ")}`}</span>
              {recap.translation && <span className="chip text-cyan-200">🌐 {langMeta(recap.language)?.native} · {recap.translation.verified ? "translation re-verified" : "English fallback"}</span>}
              <span className="chip text-slate-400">{recap.status === "in_progress" ? "Live update (match in progress)" : "Full-time recap"} · {recap.model}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
