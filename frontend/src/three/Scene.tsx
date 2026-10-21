import { Suspense, useMemo, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import { useStore } from "../lib/store";
import { Pitch, Stadium } from "./Pitch";
import { Ball, Players } from "./Players";
import { CameraRig, Heatmap, Overlays } from "./Overlays";
import { DragPlane, WhatIfOverlay } from "./WhatIfLayer";

export default function Scene() {
  const teams = useStore((s) => s.teams);
  const scene = useStore((s) => s.scene);
  const whatIfActive = useStore((s) => s.whatIf.active);
  const dragging = useStore((s) => s.whatIf.dragging);
  const controls = useRef<any>(null);
  const highlighted = useMemo(() => {
    const ids = new Set<string>();
    scene.commands.filter((c) => c.type === "highlight_players").forEach((c) => c.player_ids.forEach((p: string) => ids.add(p)));
    return ids;
  }, [scene]);
  const homeId = useStore((s) => s.homeId);
  const awayId = useStore((s) => s.awayId);
  const home = teams[homeId]?.colors.primary ?? "#3BA4F6";
  const away = teams[awayId]?.colors.primary ?? "#F2555A";
  return (
    <Canvas shadows dpr={[1, 1.5]} performance={{ min: 0.6 }} camera={{ position: [0, 46, 72], fov: 42, near: 0.5, far: 900 }}
            gl={{ antialias: true, powerPreference: "high-performance" }}>
      <color attach="background" args={["#04060b"]} />
      <fog attach="fog" args={["#04060b", 140, 330]} />
      <Suspense fallback={null}>
        <Stars radius={260} depth={60} count={1200} factor={5} fade speed={0.4} />
        <ambientLight intensity={0.38} />
        <hemisphereLight args={["#bae6fd", "#052e16", 0.45]} />
        <directionalLight position={[40, 80, 30]} intensity={1.6} castShadow shadow-mapSize={[1024, 1024]}
                          shadow-camera-left={-70} shadow-camera-right={70} shadow-camera-top={50} shadow-camera-bottom={-50} />
        {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([x, z], i) => (
          <spotLight key={i} position={[x * 74, 33, z * 56]} angle={0.55} penumbra={0.6} intensity={900} distance={220} color="#f8fafc" />
        ))}
        <Pitch />
        <Stadium home={home} away={away} />
        <Heatmap />
        {!whatIfActive && <Overlays commands={scene.commands} ghost={scene.ghost} />}
        <WhatIfOverlay />
        <DragPlane />
        <Players highlighted={highlighted} />
        <Ball />
      </Suspense>
      <OrbitControls ref={controls} makeDefault enableDamping enabled={!dragging} maxPolarAngle={Math.PI / 2.15} minDistance={18} maxDistance={190} target={[0, 0, 0]} />
      <CameraRig controls={controls} />
    </Canvas>
  );
}
