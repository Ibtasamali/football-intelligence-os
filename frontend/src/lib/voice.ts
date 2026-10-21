import { api } from "./api";

let current: HTMLAudioElement | null = null;
let speaking = false;
const listeners = new Set<(s: boolean) => void>();

export const onSpeaking = (fn: (s: boolean) => void) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};
const setSpeaking = (s: boolean) => {
  speaking = s;
  listeners.forEach((l) => l(s));
};
export const isSpeaking = () => speaking;

let endResolver: (() => void) | null = null;
const finish = () => {
  setSpeaking(false);
  endResolver?.();
  endResolver = null;
};

/** Azure neural voice per persona/language (server-side, cached); falls back to the browser voice.
 *  Resolves when speech finishes or is interrupted. */
export async function speak(text: string, persona?: string, language = "en", locale?: string): Promise<void> {
  // dev-only narration log: the video recorder rebuilds this as a clean Azure-voice soundtrack
  if (import.meta.env.DEV && typeof window !== "undefined") ((window as any).__fiosSpeech ??= []).push({ t: Date.now(), text, persona, language });
  stopSpeaking();
  setSpeaking(true);
  const done = new Promise<void>((r) => { endResolver = r; });
  try {
    const blob = await api.tts(text, persona, language);
    if (blob && speaking) {
      const audio = new Audio(URL.createObjectURL(blob));
      current = audio;
      audio.onended = finish;
      audio.onerror = finish;
      await audio.play();
      return done;
    }
  } catch {
    /* fall through to browser voice */
  }
  if (!speaking) return done;
  if ("speechSynthesis" in window) {
    const u = new SpeechSynthesisUtterance(text);
    if (locale) u.lang = locale;
    u.rate = persona === "kids" ? 0.95 : 1.03;
    u.onend = finish;
    u.onerror = finish;
    speechSynthesis.speak(u);
  } else finish();
  return done;
}

/** Instant local filler line (no network) so a live conversation never feels silent while the agents work. */
export function quickSay(text: string, locale = "en-US") {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = locale;
  u.rate = 1.08;
  u.volume = 0.8;
  speechSynthesis.speak(u);
}

export function stopSpeaking() {
  current?.pause();
  current = null;
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  finish();
}

type Rec = { start: () => void; stop: () => void; onresult: any; onend: any; onerror: any; interimResults: boolean; lang: string; continuous: boolean };

export function createRecognizer(locale = "en-US"): Rec | null {
  const W = window as any;
  const Ctor = W.SpeechRecognition || W.webkitSpeechRecognition;
  if (!Ctor) return null;
  const r: Rec = new Ctor();
  r.lang = locale;
  r.interimResults = true;
  r.continuous = false;
  return r;
}
