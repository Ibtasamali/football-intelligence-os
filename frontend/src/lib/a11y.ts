/**
 * Accessibility mode: live audio description for blind and low-vision fans, high contrast, large text,
 * reduced motion, screen-reader announcements and keyboard shortcuts.
 */
import { create } from "zustand";
import { speak } from "./voice";

export interface A11yState {
  enabled: boolean;
  contrast: boolean;
  large: boolean;
  audio: boolean;          // live audio description
  reducedMotion: boolean;
  lastAnnouncement: string;
  set: (p: Partial<A11yState>) => void;
}

const saved = (() => { try { return JSON.parse(localStorage.getItem("fios.a11y") || "{}"); } catch { return {}; } })();

export const useA11y = create<A11yState>((set, get) => ({
  enabled: false, contrast: true, large: true, audio: true, reducedMotion: true, lastAnnouncement: "", ...saved,
  set: (p) => {
    set(p);
    const { enabled, contrast, large, audio, reducedMotion } = { ...get(), ...p };
    try { localStorage.setItem("fios.a11y", JSON.stringify({ enabled, contrast, large, audio, reducedMotion })); } catch { /* ignore */ }
    applyClasses();
  },
}));

export function applyClasses() {
  const s = useA11y.getState();
  const root = document.documentElement;
  root.classList.toggle("a11y-contrast", s.enabled && s.contrast);
  root.classList.toggle("a11y-large", s.enabled && s.large);
}

// ---- sequential speech queue (descriptions never cut each other off)
const queue: string[] = [];
let busy = false;
async function pump(persona: string, lang: string) {
  if (busy) return;
  busy = true;
  while (queue.length) {
    const t = queue.shift()!;
    useA11y.setState({ lastAnnouncement: t });
    await speak(t, persona, lang);
  }
  busy = false;
}

export function announce(text: string, opts: { persona?: string; lang?: string; urgent?: boolean } = {}) {
  const s = useA11y.getState();
  if (!s.enabled || !text) return;
  useA11y.setState({ lastAnnouncement: text });           // screen readers via aria-live, even without audio
  if (!s.audio) return;
  if (opts.urgent) queue.unshift(text); else queue.push(text);
  while (queue.length > 4) queue.splice(1, 1);            // never fall far behind the live action
  pump(opts.persona ?? "tactical_analyst", opts.lang ?? "en");
}

const SIDE = (y: number | null | undefined) => (y == null ? "" : y < 22 ? " on the right" : y > 46 ? " on the left" : " centrally");

/** Plain-language description of an important event (for audio description). */
export function describeEvent(ev: any, teamName: (id: string) => string): string | null {
  const team = ev.team ? teamName(ev.team) : "";
  const who = ev.player ? `${ev.player} of ${team}` : team;
  switch (ev.type) {
    case "GOAL": return `Goal! ${who} scores at ${ev.clock}.`;
    case "SHOT": return `Shot by ${who}${ev.xg != null ? `, a ${ev.xg >= 0.3 ? "big" : ev.xg >= 0.1 ? "decent" : "low-quality"} chance` : ""} — ${String(ev.outcome || "").replace("_", " ")}.`;
    case "SAVE": return `Saved by ${who}.`;
    case "CARD": return `${ev.outcome === "red" ? "Red" : "Yellow"} card for ${who}.`;
    case "SUBSTITUTION": return `Substitution for ${team}: ${ev.player} comes on.`;
    case "CORNER": return `Corner to ${team}${SIDE(ev.y)}.`;
    case "HALF_TIME": return "Half-time.";
    case "FULL_TIME": return "Full time.";
    default: return null;
  }
}
