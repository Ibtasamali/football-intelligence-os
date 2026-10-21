import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import { useStore } from "../lib/store";
import type { MatchEvent, Position } from "../lib/types";
import { toWorld } from "./coords";

function numberTexture(n: number, color: string) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = color;
  g.beginPath();
  g.arc(64, 64, 54, 0, Math.PI * 2);
  g.fill();
  g.lineWidth = 8;
  g.strokeStyle = "rgba(255,255,255,0.9)";
  g.stroke();
  g.fillStyle = "white";
  g.font = "bold 62px 'Space Grotesk', Inter, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(String(n), 64, 68);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** Source of truth for what the pitch shows: replay frames when replaying an insight, live otherwise. */
export function useFramePositions(): { positions: Position[]; event: MatchEvent | null } {
  const live = useStore((s) => s.positions);
  const lastEvent = useStore((s) => s.lastEvent);
  const frames = useStore((s) => s.replayFrames);
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    if (!frames?.length) return;
    setFrame(0);
    const id = setInterval(() => setFrame((f) => (f + 1) % (frames.length + 3)), 650);
    return () => clearInterval(id);
  }, [frames]);
  if (frames?.length) {
    const ev = frames[Math.min(frame, frames.length - 1)];
    return { positions: ev.positions ?? live, event: ev };
  }
  return { positions: live, event: lastEvent };
}

function PlayerMesh({ p, color, number, highlighted, onPitch, draggable, onGrab }: { p: Position; color: string; number: number; highlighted: boolean; onPitch: boolean; draggable?: boolean; onGrab?: () => void }) {
  const group = useRef<THREE.Group>(null!);
  const ring = useRef<THREE.Mesh>(null!);
  const target = useRef(new THREE.Vector3(...toWorld(p.x, p.y)));
  const trail = useRef<THREE.Vector3[]>([]);
  const lineRef = useRef<any>(null);
  const tex = useMemo(() => numberTexture(number, color), [number, color]);

  useEffect(() => {
    target.current.set(...toWorld(p.x, p.y));
  }, [p.x, p.y]);

  useFrame(({ clock }, dt) => {
    const g = group.current;
    if (!g) return;
    const k = 1 - Math.pow(0.0025, dt);
    g.position.lerp(target.current, k);
    const s = 1 + Math.sin(clock.elapsedTime * 6) * 0.18;
    if (ring.current) {
      ring.current.scale.setScalar(highlighted ? s * 1.6 : 1);
      (ring.current.material as THREE.MeshBasicMaterial).opacity = highlighted ? 0.95 : 0.35;
    }
    if (highlighted) {
      const last = trail.current[trail.current.length - 1];
      if (!last || last.distanceTo(g.position) > 0.6) {
        trail.current.push(g.position.clone().setY(0.06));
        if (trail.current.length > 40) trail.current.shift();
        if (lineRef.current && trail.current.length > 1) {
          lineRef.current.geometry.setPositions(trail.current.flatMap((v) => [v.x, v.y, v.z]));
        }
      }
    } else if (trail.current.length) trail.current = [];
  });

  if (!onPitch) return null;
  return (
    <>
      <group ref={group} position={toWorld(p.x, p.y)}
             onPointerDown={draggable ? (e) => { e.stopPropagation(); onGrab?.(); } : undefined}
             onPointerOver={draggable ? () => { document.body.style.cursor = "grab"; } : undefined}
             onPointerOut={draggable ? () => { document.body.style.cursor = ""; } : undefined}>
        {draggable && (
          <mesh position={[0, 1.2, 0]}>
            <cylinderGeometry args={[1.4, 1.4, 2.6, 12]} />
            <meshBasicMaterial transparent opacity={0} depthWrite={false} />
          </mesh>
        )}
        <mesh position={[0, 0.95, 0]} castShadow>
          <capsuleGeometry args={[0.42, 1.0, 6, 14]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={highlighted ? 0.55 : 0.12} roughness={0.45} />
        </mesh>
        <mesh position={[0, 1.95, 0]} castShadow>
          <sphereGeometry args={[0.3, 16, 16]} />
          <meshStandardMaterial color="#f1d3b3" roughness={0.6} />
        </mesh>
        <mesh ref={ring} rotation-x={-Math.PI / 2} position-y={0.04}>
          <ringGeometry args={[0.75, 1.0, 40]} />
          <meshBasicMaterial color={highlighted ? "#fde047" : color} transparent opacity={0.35} />
        </mesh>
        <sprite position={[0, 3.0, 0]} scale={[1.3, 1.3, 1.3]}>
          <spriteMaterial map={tex} depthTest={false} transparent />
        </sprite>
      </group>
      {highlighted && (
        <Line ref={lineRef} points={[[0, 0, 0], [0, 0, 0.01]]} color="#fde047" lineWidth={2} transparent opacity={0.6} />
      )}
    </>
  );
}

export function Players({ highlighted }: { highlighted: Set<string> }) {
  const live = useFramePositions().positions;
  const roster = useStore((s) => s.roster);
  const teams = useStore((s) => s.teams);
  const whatIf = useStore((s) => s.whatIf);
  const setWhatIf = useStore((s) => s.setWhatIf);
  const positions = whatIf.active
    ? whatIf.base.map((p) => (whatIf.moves[p.player_id] ? { ...p, x: whatIf.moves[p.player_id][0], y: whatIf.moves[p.player_id][1] } : p))
    : live;
  return (
    <group>
      {positions.map((p) => (
        <PlayerMesh key={p.player_id} p={p} onPitch color={teams[p.team_id]?.colors.primary ?? "#999"}
                    number={roster[p.player_id]?.number ?? 0}
                    highlighted={whatIf.active ? whatIf.moves[p.player_id] !== undefined || whatIf.dragging === p.player_id : highlighted.has(p.player_id)}
                    draggable={whatIf.active} onGrab={() => setWhatIf({ dragging: p.player_id })} />
      ))}
    </group>
  );
}

export function Ball() {
  const { event } = useFramePositions();
  const mesh = useRef<THREE.Mesh>(null!);
  const from = useRef(new THREE.Vector3());
  const to = useRef(new THREE.Vector3());
  const t0 = useRef(0);
  const arc = useRef(0);
  useEffect(() => {
    if (!event || event.x == null) return;
    const sx = event.x, sy = event.y!;
    const ex = event.end_x ?? sx, ey = event.end_y ?? sy;
    from.current.copy(mesh.current?.position ?? new THREE.Vector3(...toWorld(sx, sy, 0.22)));
    to.current.set(...toWorld(ex, ey, 0.22));
    const dist = Math.hypot(ex - sx, ey - sy);
    arc.current = event.type === "PASS" && dist > 22 ? Math.min(6, dist / 6) : event.type === "SHOT" ? 1.2 : 0.15;
    t0.current = performance.now();
  }, [event?.event_id]);
  useFrame(() => {
    if (!mesh.current) return;
    const u = Math.min(1, (performance.now() - t0.current) / 550);
    const e = 1 - Math.pow(1 - u, 3);
    mesh.current.position.lerpVectors(from.current, to.current, e);
    mesh.current.position.y = 0.22 + Math.sin(Math.PI * e) * arc.current;
    mesh.current.rotation.x += 0.2;
  });
  return (
    <mesh ref={mesh} castShadow position={[0, 0.22, 0]}>
      <icosahedronGeometry args={[0.24, 2]} />
      <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.6} roughness={0.3} />
    </mesh>
  );
}
