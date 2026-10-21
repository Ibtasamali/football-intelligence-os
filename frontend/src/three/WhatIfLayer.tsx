import { useMemo } from "react";
import * as THREE from "three";
import { Line } from "@react-three/drei";
import { useStore } from "../lib/store";
import { movePlayer, runWhatIf } from "../lib/whatif";
import { L, W, toWorld } from "./coords";

/** Invisible ground plane that turns pointer movement into player moves while dragging. */
export function DragPlane() {
  const dragging = useStore((s) => s.whatIf.dragging);
  const active = useStore((s) => s.whatIf.active);
  const setWhatIf = useStore((s) => s.setWhatIf);
  if (!active) return null;
  const end = () => {
    if (!useStore.getState().whatIf.dragging) return;
    setWhatIf({ dragging: null });
    document.body.style.cursor = "";
    runWhatIf();
  };
  return (
    <mesh rotation-x={-Math.PI / 2} position-y={0.02}
          onPointerMove={(e) => { if (dragging) { e.stopPropagation(); movePlayer(dragging, e.point.x + L / 2, e.point.z + W / 2); } }}
          onPointerUp={end} onPointerLeave={end}>
      <planeGeometry args={[L + 20, W + 20]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} />
    </mesh>
  );
}

/** Pitch-control heatmap, ghost rings at original positions and open/blocked passing lanes. */
export function WhatIfOverlay() {
  const wi = useStore((s) => s.whatIf);
  const teams = useStore((s) => s.teams);
  const res = wi.result;
  const color = res ? teams[res.attacking_team]?.colors.primary ?? "#22d3ee" : "#22d3ee";
  const tex = useMemo(() => {
    if (!res?.grid) return null;
    const { nx, ny, control_after } = res.grid;
    const c = document.createElement("canvas");
    c.width = nx;
    c.height = ny;
    const g = c.getContext("2d")!;
    const att = new THREE.Color(color);
    const def = new THREE.Color("#f8fafc");
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const v = control_after[j][i];
        const col = v >= 0.5 ? att : def;
        const a = Math.abs(v - 0.5) * 2 * 0.55;
        g.fillStyle = `rgba(${Math.round(col.r * 255)},${Math.round(col.g * 255)},${Math.round(col.b * 255)},${a.toFixed(3)})`;
        g.fillRect(i, j, 1, 1);
      }
    }
    const t = new THREE.CanvasTexture(c);
    t.magFilter = THREE.LinearFilter;
    return t;
  }, [res, color]);
  if (!wi.active) return null;
  return (
    <group>
      {tex && (
        <mesh rotation-x={-Math.PI / 2} position-y={0.03}>
          <planeGeometry args={[L, W]} />
          <meshBasicMaterial map={tex} transparent depthWrite={false} />
        </mesh>
      )}
      {res?.moved?.map((m: any) => (
        <group key={m.player_id}>
          <mesh rotation-x={-Math.PI / 2} position={toWorld(m.from[0], m.from[1], 0.06)}>
            <ringGeometry args={[0.8, 1.1, 32]} />
            <meshBasicMaterial color="#e879f9" transparent opacity={0.8} />
          </mesh>
          <Line points={[toWorld(m.from[0], m.from[1], 0.08), toWorld(m.to[0], m.to[1], 0.08)]} color="#e879f9" lineWidth={2} dashed dashSize={1} gapSize={0.6} />
        </group>
      ))}
      {res?.after?.passing_options?.map((o: any) => (
        <Line key={o.to} points={[toWorld(o.from_xy[0], o.from_xy[1], 0.15), toWorld(o.to_xy[0], o.to_xy[1], 0.15)]}
              color={o.open ? "#34d399" : "#f87171"} lineWidth={o.open ? 2.5 : 1.5} dashed={!o.open} dashSize={0.8} gapSize={0.5}
              transparent opacity={0.85} />
      ))}
    </group>
  );
}
