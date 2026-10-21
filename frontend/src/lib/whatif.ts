import { api } from "./api";
import { useStore } from "./store";

let timer: number | undefined;

/** Freeze the current frame and open the what-if sandbox. */
export async function enterWhatIf() {
  const s = useStore.getState();
  if (s.replay?.running) s.set({ replay: await api.replay(s.matchId, "pause") });
  const base = s.positions;
  if (!base.length) return;
  s.setWhatIf({ active: true, base, moves: {}, result: null, loading: true, dragging: null, eventId: s.lastEvent?.event_id, clock: s.lastEvent?.clock });
  const res = await api.whatif(s.matchId, { event_id: s.lastEvent?.event_id, moves: {}, explain: false });
  useStore.getState().setWhatIf({ result: res, loading: false, eventId: res.event_id, clock: res.clock });
}

export function exitWhatIf() {
  useStore.getState().setWhatIf({ active: false, moves: {}, result: null, dragging: null });
}

export function resetWhatIf() {
  useStore.getState().setWhatIf({ moves: {} });
  runWhatIf(0);
}

export function movePlayer(pid: string, x: number, y: number) {
  const s = useStore.getState();
  s.setWhatIf({ moves: { ...s.whatIf.moves, [pid]: [Math.max(0, Math.min(105, x)), Math.max(0, Math.min(68, y))] } });
}

/** Recompute (debounced) after a drag ends. */
export function runWhatIf(delay = 250) {
  clearTimeout(timer);
  timer = window.setTimeout(async () => {
    const s = useStore.getState();
    s.setWhatIf({ loading: true });
    try {
      const res = await api.whatif(s.matchId, { event_id: s.whatIf.eventId, moves: s.whatIf.moves, explain: Object.keys(s.whatIf.moves).length > 0 });
      useStore.getState().setWhatIf({ result: res, loading: false });
    } catch {
      useStore.getState().setWhatIf({ loading: false });
    }
  }, delay);
}

if (import.meta.env.DEV && typeof window !== "undefined") Object.assign((window as any).__fios ?? ((window as any).__fios = {}), { whatif: { enterWhatIf, exitWhatIf, resetWhatIf, movePlayer, runWhatIf } });
