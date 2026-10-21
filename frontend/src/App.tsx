import { useEffect } from "react";
import { motion } from "framer-motion";
import { useStore } from "./lib/store";
import { bootstrap } from "./lib/live";
import TopBar from "./components/TopBar";
import NavRail from "./components/NavRail";
import Toasts from "./components/Toasts";
import WhyDrawer from "./components/WhyDrawer";
import VoiceAssistant from "./components/VoiceAssistant";
import DemoBar from "./components/DemoBar";
import ErrorBoundary from "./components/ErrorBoundary";
import LiveScreen from "./screens/LiveScreen";
import PipelineScreen from "./screens/PipelineScreen";
import RecapScreen from "./screens/RecapScreen";
import { MotionConfig } from "framer-motion";
import { useA11y } from "./lib/a11y";
import TacticsScreen from "./screens/TacticsScreen";
import StoryScreen from "./screens/StoryScreen";
import PlayersScreen from "./screens/PlayersScreen";
import TeamsScreen from "./screens/TeamsScreen";
import AgentsScreen from "./screens/AgentsScreen";
import HistoryScreen from "./screens/HistoryScreen";
import FanScreen from "./screens/FanScreen";
import CoachScreen from "./screens/CoachScreen";
import TracingScreen from "./screens/TracingScreen";
import JudgeTour from "./components/JudgeTour";

const SCREENS = { live: LiveScreen, pipeline: PipelineScreen, studio: RecapScreen, coach: CoachScreen, tactics: TacticsScreen, story: StoryScreen, players: PlayersScreen, teams: TeamsScreen,
  agents: AgentsScreen, traces: TracingScreen, history: HistoryScreen, fan: FanScreen };

export default function App() {
  const screen = useStore((s) => s.screen);
  const matchId = useStore((s) => s.matchId);
  useEffect(() => { bootstrap(matchId).catch((e) => console.error(e)); }, [matchId]);
  useEffect(() => {
    const fromHash = () => {
      const h = location.hash.slice(1);
      if (h && h in SCREENS) useStore.getState().set({ screen: h as keyof typeof SCREENS });
    };
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);
  useEffect(() => { if (location.hash.slice(1) !== screen) history.replaceState(null, "", `#${screen}`); }, [screen]);
  const Screen = SCREENS[screen];
  const reduce = useA11y((a) => a.enabled && a.reducedMotion);
  return (
    <MotionConfig reducedMotion={reduce ? "always" : "never"}>
    <div className="grid-bg flex h-full flex-col">
      <ErrorBoundary name="topbar"><TopBar /></ErrorBoundary>
      <div className="flex min-h-0 flex-1">
        <NavRail />
        <main className="relative min-w-0 flex-1">
          {/* keep the 3D scene mounted so it never rebuilds */}
          <div className={screen === "live" ? "h-full" : "hidden"}><ErrorBoundary name="live"><LiveScreen /></ErrorBoundary></div>
          {screen !== "live" && (
            <motion.div key={screen} className="absolute inset-0" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}>
              <ErrorBoundary name={screen}><Screen /></ErrorBoundary>
            </motion.div>
          )}
        </main>
      </div>
      <Toasts />
      <DemoBar />
      <ErrorBoundary name="why"><WhyDrawer /></ErrorBoundary>
      <ErrorBoundary name="assistant"><VoiceAssistant /></ErrorBoundary>
      <JudgeTour />
    </div>
    </MotionConfig>
  );
}
