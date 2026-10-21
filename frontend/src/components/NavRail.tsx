import { Activity, BarChart3, BookOpen, Bot, Clapperboard, FileText, History, LayoutGrid, Map, User, Users, Workflow } from "lucide-react";
import { useStore, type Screen } from "../lib/store";

const ITEMS: { id: Screen; label: string; icon: any }[] = [
  { id: "live", label: "Live", icon: Activity },
  { id: "pipeline", label: "Pipeline", icon: Workflow },
  { id: "studio", label: "Studio", icon: Clapperboard },
  { id: "coach", label: "Coach", icon: FileText },
  { id: "tactics", label: "Tactics", icon: Map },
  { id: "story", label: "Story", icon: BookOpen },
  { id: "players", label: "Players", icon: Users },
  { id: "teams", label: "Teams", icon: LayoutGrid },
  { id: "history", label: "History", icon: History },
  { id: "agents", label: "Agents", icon: Bot },
  { id: "traces", label: "Traces", icon: BarChart3 },
  { id: "fan", label: "Fan", icon: User },
];

export default function NavRail() {
  const screen = useStore((s) => s.screen);
  const set = useStore((s) => s.set);
  const running = useStore((s) => s.runs.filter((r) => !r.done).length);
  return (
    <nav className="z-10 flex w-[72px] flex-col items-center gap-1 overflow-y-auto border-r border-white/[0.06] bg-ink-950/70 py-3 backdrop-blur-xl">
      {ITEMS.map(({ id, label, icon: Icon }) => (
        <button key={id} data-tour={id} onClick={() => set({ screen: id })}
                className={`group relative flex w-14 flex-col items-center gap-1 rounded-xl py-2 text-[10px] font-medium transition ${
                  screen === id ? "bg-cyan-400/10 text-cyan-200" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}>
          {screen === id && <span className="absolute left-0 top-2 h-8 w-[3px] rounded-r bg-cyan-300" />}
          <Icon size={18} />
          {label}
          {id === "agents" && running > 0 && (
            <span className="absolute right-2 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-cyan-400 px-1 text-[9px] font-bold text-ink-950">{running}</span>
          )}
        </button>
      ))}
    </nav>
  );
}
