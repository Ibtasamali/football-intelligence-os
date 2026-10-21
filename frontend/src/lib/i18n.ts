import { useEffect, useState } from "react";
import type { Insight } from "./types";

export interface Lang { code: string; name: string; native: string; locale: string; rtl: boolean }
export interface Localized { language: string; verified: boolean; cached: boolean; headline: string; explanation: string;
  commentary: string; historical_note: string; voice: string; issues: string[] }

let langs: Lang[] = [];
export async function loadLanguages(): Promise<Lang[]> {
  if (!langs.length) langs = (await fetch("/api/voice/languages").then((r) => r.json())).languages;
  return langs;
}
export const langMeta = (code: string): Lang | undefined => langs.find((l) => l.code === code);

const cache = new Map<string, Promise<Localized>>();
// A tiny queue: at most 2 translation requests in flight, so translations never starve other API calls
// (browsers allow only ~6 parallel requests per host).
let inFlight = 0;
const queue: (() => void)[] = [];
const pump = () => {
  while (inFlight < 2 && queue.length) {
    inFlight++;
    queue.shift()!();
  }
};

/** Verified, server-cached translation of one insight (one per language, shared by every fan). */
export function translateInsight(ins: Insight, language: string, level: string, persona: string, isCurrent: () => boolean = () => true): Promise<Localized> {
  const key = `${ins.insight_id}|${language}|${level}|${persona}`;
  if (!cache.has(key)) {
    const p = new Promise<Localized>((resolve, reject) => {
      queue.push(() => {
        if (!isCurrent()) {  // language changed while queued → drop it
          inFlight--; cache.delete(key); pump(); reject(new Error("stale")); return;
        }
        fetch(`/api/insights/${ins.insight_id}/translate`, {
          method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ language, level, persona }),
        }).then((r) => r.json()).then(resolve, (e) => { cache.delete(key); reject(e); })
          .finally(() => { inFlight--; pump(); });
      });
      pump();
    });
    cache.set(key, p);
  }
  return cache.get(key)!;
}

export function useLocalized(ins: Insight, language: string, level: string, persona: string, enabled = true): Localized | null {
  const [loc, setLoc] = useState<Localized | null>(null);
  useEffect(() => {
    setLoc(null);
    if (!enabled || !language || language === "en" || ins.category === "ANSWER") return;
    let alive = true;
    translateInsight(ins, language, level, persona, () => alive).then((l) => alive && setLoc(l)).catch(() => {});
    return () => { alive = false; };
  }, [ins.insight_id, language, level, persona, enabled]);
  return loc;
}
