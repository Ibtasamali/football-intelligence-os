import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import { Panel } from "../components/ui";
import type { FanProfile } from "../lib/types";
import { type Lang, loadLanguages } from "../lib/i18n";

const LEVELS = ["beginner", "intermediate", "advanced", "professional"] as const;
const PERSONAS = [["casual_commentator", "Casual commentator"], ["tactical_analyst", "Tactical analyst"], ["coach", "Coach"], ["kids", "Kids mode"], ["expert_analyst", "Expert analyst"]];

export default function FanScreen() {
  const { profile, set, teams, roster, insights } = useStore();
  const [fans, setFans] = useState<FanProfile[]>([]);
  const [mem, setMem] = useState<any[]>([]);
  const [langs, setLangs] = useState<Lang[]>([]);
  useEffect(() => { loadLanguages().then(setLangs); }, []);
  useEffect(() => { api.fans().then((f) => setFans(f.fans)); }, []);
  useEffect(() => { api.fan(profile.user_id).then((f) => setMem(f.memories ?? [])).catch(() => setMem([])); }, [profile.user_id]);
  const save = async (patch: Partial<FanProfile>) => {
    const next = await api.saveFan(profile.user_id, { ...patch });
    set({ profile: next });
  };
  const sample = [...insights].reverse().find((i) => i.significance >= 0.6 && i.category !== "ANSWER");
  return (
    <div className="grid h-full grid-cols-[1fr_1.2fr] gap-3 p-3">
      <Panel title="Fan profile — personalisation without extra LLM calls">
        <div className="space-y-5 overflow-y-auto p-5">
          <div>
            <div className="label mb-2">Who's watching</div>
            <div className="flex flex-wrap gap-2">
              {fans.map((f) => <button key={f.user_id} onClick={() => set({ profile: f })} className={`chip px-3 py-1 text-[12px] ${profile.user_id === f.user_id ? "border-cyan-300/60 text-cyan-100" : ""}`}>{f.display_name}</button>)}
            </div>
          </div>
          <Field label="Favourite team">
            {Object.entries(teams).map(([id, t]) => <button key={id} onClick={() => save({ favorite_team_id: id })} className={`chip px-3 py-1 ${profile.favorite_team_id === id ? "border-white/40" : ""}`} style={{ color: t.colors.primary }}>{t.name}</button>)}
          </Field>
          <Field label="Favourite player">
            <select value={profile.favorite_player_id ?? ""} onChange={(e) => save({ favorite_player_id: e.target.value })} className="btn bg-ink-900">
              {Object.values(roster).map((p) => <option key={p.player_id} value={p.player_id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Knowledge level">
            {LEVELS.map((l) => <button key={l} onClick={() => save({ knowledge_level: l })} className={`chip px-3 py-1 capitalize ${profile.knowledge_level === l ? "border-cyan-300/60 bg-cyan-400/10 text-cyan-100" : ""}`}>{l}</button>)}
          </Field>
          <Field label="Language (verified translation + native neural voice)">
            {langs.map((l) => <button key={l.code} onClick={() => save({ language: l.code })} className={`chip px-3 py-1 ${(profile.language || "en") === l.code ? "border-cyan-300/60 bg-cyan-400/10 text-cyan-100" : ""}`}>{l.native}</button>)}
          </Field>
          <Field label="Commentary voice">
            {PERSONAS.map(([id, label]) => <button key={id} onClick={() => save({ persona: id })} className={`chip px-3 py-1 ${profile.persona === id ? "border-cyan-300/60 bg-cyan-400/10 text-cyan-100" : ""}`}>{label}</button>)}
          </Field>
          <div>
            <div className="label mb-2">What the AI remembers about {profile.display_name} (MAG)</div>
            {mem.length ? mem.map((m) => <div key={m.memory_id} className="mb-1 text-[12px] text-slate-300">• {m.text}</div>) : <div className="text-[12px] text-slate-500">No personal memories yet — ask the Match Copilot something.</div>}
          </div>
        </div>
      </Panel>
      <Panel title="Same moment, four audiences (one shared LLM call)">
        {sample ? (
          <div className="space-y-3 overflow-y-auto p-5">
            <div className="font-mono text-xs text-slate-500">{sample.minute}' · {sample.headline}</div>
            {LEVELS.map((l) => (
              <div key={l} className={`rounded-xl border p-3 ${profile.knowledge_level === l ? "border-cyan-300/40 bg-cyan-400/[0.06]" : "border-white/[0.06]"}`}>
                <div className="label mb-1 capitalize">{l}{profile.knowledge_level === l ? " · your level" : ""}</div>
                <div className="text-[13px] text-slate-200">{sample.explanations[l]}</div>
              </div>
            ))}
            {profile.favorite_team_id && sample.perspectives?.[profile.favorite_team_id] && <div className="text-[13px] italic text-cyan-200">{sample.perspectives[profile.favorite_team_id]}</div>}
          </div>
        ) : <div className="grid h-full place-items-center text-slate-500">Start the match to see personalised explanations.</div>}
      </Panel>
    </div>
  );
}

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div><div className="label mb-2">{label}</div><div className="flex flex-wrap gap-2">{children}</div></div>
);
