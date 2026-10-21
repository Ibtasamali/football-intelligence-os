import { api } from "./api";
import { useStore } from "./store";
import type { Insight } from "./types";

let timer: number | undefined;

/** Replay the event sequence behind an insight in the 3D scene with its tactical overlays. */
export async function replayInsight(ins: Insight) {
  const s = useStore.getState();
  const cmd = ins.visualization?.find((c) => c.type === "replay");
  s.focusInsight(ins);
  if (!cmd?.event_ids?.length) return;
  const { events } = await api.positions(ins.match_id, cmd.event_ids);
  s.set({ replayFrames: events, followLive: false, screen: "live" });
  clearTimeout(timer);
  timer = window.setTimeout(() => endReplay(), (events.length + 3) * 650 * 2);
}

export function endReplay() {
  clearTimeout(timer);
  useStore.getState().set({ replayFrames: null, followLive: true });
}
