import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { Html, Line, QuadraticBezierLine } from "@react-three/drei";
import type { SceneCommand } from "../lib/types";
import { useStore } from "../lib/store";
import { L, W, toWorld } from "./coords";

function Zone({ cmd, ghost }: { cmd: SceneCommand; ghost?: boolean }) {
  const { x0, x1, y0, y1 } = cmd.zone;
  const mat = useRef<THREE.MeshBasicMaterial>(null!);
  const [cx, , cz] = toWorld((x0 + x1) / 2, (y0 + y1) / 2);
  const w = x1 - x0;
  const d = y1 - y0;
  useFrame(({ clock }) => {
    if (mat.current) mat.current.opacity = (ghost ? 0.1 : 0.16) + Math.sin(clock.elapsedTime * 2.4) * 0.07;
  });
  const border = [
    toWorld(x0, y0, 0.08), toWorld(x1, y0, 0.08), toWorld(x1, y1, 0.08), toWorld(x0, y1, 0.08), toWorld(x0, y0, 0.08),
  ] as [number, number, number][];
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[cx, 0.05, cz]}>
        <planeGeometry args={[w, d]} />
        <meshBasicMaterial ref={mat} color={cmd.color} transparent opacity={0.18} depthWrite={false} />
      </mesh>
      <Line points={border} color={cmd.color} lineWidth={ghost ? 1.5 : 3} dashed={ghost} dashSize={1.5} gapSize={1} />
      <Html position={[cx, 4.5, cz]} center distanceFactor={70} zIndexRange={[10, 0]}>
        <div className="pointer-events-none whitespace-nowrap rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider backdrop-blur-md"
             style={{ borderColor: cmd.color, color: cmd.color, background: "rgba(4,6,11,.72)" }}>
          {ghost ? "Then · " : ""}{cmd.label}
        </div>
      </Html>
    </group>
  );
}

function Trajectory({ cmd }: { cmd: SceneCommand }) {
  const [a, b] = [cmd.from, cmd.to];
  const start = toWorld(a[0], a[1], 0.25);
  const end = toWorld(b[0], b[1], 0.25);
  const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const mid: [number, number, number] = [(start[0] + end[0]) / 2, Math.min(7, 0.6 + dist / 6), (start[2] + end[2]) / 2];
  const color = cmd.kind === "shot" ? "#fde047" : cmd.kind === "carry" ? "#a78bfa" : cmd.success ? "#e0f2fe" : "#f87171";
  return (
    <group>
      <QuadraticBezierLine start={start} end={end} mid={cmd.kind === "carry" ? [mid[0], 0.3, mid[2]] : mid}
                           color={color} lineWidth={cmd.kind === "shot" ? 3.5 : 2.2} dashed={cmd.kind === "carry"} dashSize={0.8} gapSize={0.5} />
      <mesh position={end}>
        <sphereGeometry args={[0.28, 12, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  );
}

function Lanes({ cmd }: { cmd: SceneCommand }) {
  const max = Math.max(...cmd.lanes.map((l: any) => l.count));
  return (
    <group>
      {cmd.lanes.map((l: any, i: number) => {
        const s = toWorld(l.from[0], l.from[1], 0.12);
        const e = toWorld(l.to[0], l.to[1], 0.12);
        return <QuadraticBezierLine key={i} start={s} end={e} mid={[(s[0] + e[0]) / 2, 2.5, (s[2] + e[2]) / 2]}
                                    color={cmd.color} lineWidth={1 + (5 * l.count) / max} transparent opacity={0.75} />;
      })}
    </group>
  );
}

function Pulse({ cmd }: { cmd: SceneCommand }) {
  const ref = useRef<THREE.Mesh>(null!);
  const pos = toWorld(cmd.at[0], cmd.at[1], 0.07);
  useFrame(({ clock }) => {
    const t = (clock.elapsedTime % 1.6) / 1.6;
    ref.current.scale.setScalar(1 + t * 6);
    (ref.current.material as THREE.MeshBasicMaterial).opacity = 0.8 * (1 - t);
  });
  return (
    <group>
      <mesh ref={ref} rotation-x={-Math.PI / 2} position={pos}>
        <ringGeometry args={[0.6, 0.85, 48]} />
        <meshBasicMaterial color={cmd.color} transparent />
      </mesh>
      {cmd.label && (
        <Html position={[pos[0], 3, pos[2]]} center distanceFactor={60}>
          <div className="pointer-events-none rounded-md bg-black/70 px-2 py-0.5 font-mono text-[11px] text-yellow-300">{cmd.label}</div>
        </Html>
      )}
    </group>
  );
}

function DefLine({ cmd }: { cmd: SceneCommand }) {
  return (
    <group>
      <Line points={[toWorld(cmd.x, 0, 0.1), toWorld(cmd.x, W, 0.1)]} color="#a78bfa" lineWidth={3} dashed dashSize={2} gapSize={1} />
      <Html position={toWorld(cmd.x, -2, 1.2)} center distanceFactor={70}>
        <div className="pointer-events-none whitespace-nowrap rounded bg-violet-500/20 px-2 py-0.5 text-[11px] text-violet-200">{cmd.label}</div>
      </Html>
    </group>
  );
}

export function Overlays({ commands, ghost }: { commands: SceneCommand[]; ghost?: SceneCommand[] }) {
  return (
    <group>
      {commands.map((c, i) => {
        switch (c.type) {
          case "highlight_zone": return <Zone key={i} cmd={c} />;
          case "trajectory": return <Trajectory key={i} cmd={c} />;
          case "passing_lanes": return <Lanes key={i} cmd={c} />;
          case "pulse": return <Pulse key={i} cmd={c} />;
          case "defensive_line": return <DefLine key={i} cmd={c} />;
          default: return null;
        }
      })}
      {ghost?.map((c, i) => (c.type === "highlight_zone" ? <Zone key={`g${i}`} cmd={c} ghost /> : null))}
    </group>
  );
}

/** Touch-density heatmap for one team, rendered to a canvas texture. */
export function Heatmap() {
  const team = useStore((s) => s.heatTeam);
  const touches = useStore((s) => (s.heatTeam ? s.touches[s.heatTeam] : null));
  const color = useStore((s) => (s.heatTeam ? s.teams[s.heatTeam]?.colors.primary : "#fff"));
  const tex = useMemo(() => {
    if (!touches?.length) return null;
    const c = document.createElement("canvas");
    c.width = 420;
    c.height = 272;
    const g = c.getContext("2d")!;
    g.globalCompositeOperation = "lighter";
    for (const [x, y] of touches) {
      const px = (x / L) * c.width, py = (y / W) * c.height;
      const grd = g.createRadialGradient(px, py, 0, px, py, 26);
      grd.addColorStop(0, "rgba(255,255,255,0.13)");
      grd.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = grd;
      g.fillRect(px - 26, py - 26, 52, 52);
    }
    g.globalCompositeOperation = "source-in";
    const lin = g.createLinearGradient(0, 0, c.width, 0);
    lin.addColorStop(0, color!);
    lin.addColorStop(1, color!);
    g.fillStyle = lin;
    g.fillRect(0, 0, c.width, c.height);
    const t = new THREE.CanvasTexture(c);
    return t;
  }, [touches?.length, team, color]);
  if (!tex) return null;
  return (
    <mesh rotation-x={-Math.PI / 2} position-y={0.03}>
      <planeGeometry args={[L, W]} />
      <meshBasicMaterial map={tex} transparent opacity={0.85} depthWrite={false} />
    </mesh>
  );
}

const PRESETS: Record<string, (f: [number, number]) => { pos: THREE.Vector3; look: THREE.Vector3 }> = {
  broadcast: ([fx]) => ({ pos: new THREE.Vector3(fx * 0.55, 38, 68), look: new THREE.Vector3(fx * 0.6, 0, 0) }),
  tactical: ([fx, fz]) => ({ pos: new THREE.Vector3(fx * 0.8, 62, fz * 0.6 + 26), look: new THREE.Vector3(fx * 0.85, 0, fz * 0.6) }),
  overhead: () => ({ pos: new THREE.Vector3(0, 95, 1), look: new THREE.Vector3(0, 0, 0) }),
};

export function CameraRig({ controls }: { controls: React.MutableRefObject<any> }) {
  const cmds = useStore((s) => s.scene.commands);
  const source = useStore((s) => s.scene.source);
  const { camera } = useThree();
  const goal = useRef<{ pos: THREE.Vector3; look: THREE.Vector3 } | null>(null);
  const until = useRef(0);
  useEffect(() => {
    const cam = cmds.find((c) => c.type === "camera");
    if (!cam) return;
    const [fx, fy] = cam.focus ?? [52.5, 34];
    const [wx, , wz] = toWorld(fx, fy);
    goal.current = (PRESETS[cam.preset] ?? PRESETS.broadcast)([wx, wz]);
    until.current = performance.now() + 1800;
  }, [source]);
  useFrame(() => {
    if (!goal.current || performance.now() > until.current) return;
    camera.position.lerp(goal.current.pos, 0.05);
    if (controls.current) {
      controls.current.target.lerp(goal.current.look, 0.05);
      controls.current.update();
    }
  });
  return null;
}
