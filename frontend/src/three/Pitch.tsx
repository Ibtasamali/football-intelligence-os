import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { L, W } from "./coords";

const PX = 12; // texture pixels per metre
const MARGIN = 6;

function drawPitch(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  const TW = (L + MARGIN * 2) * PX;
  const TH = (W + MARGIN * 2) * PX;
  c.width = TW;
  c.height = TH;
  const g = c.getContext("2d")!;
  // grass with mowing stripes
  const stripes = 18;
  for (let i = 0; i < stripes; i++) {
    g.fillStyle = i % 2 ? "#14532d" : "#166534";
    g.fillRect((i * TW) / stripes, 0, TW / stripes + 1, TH);
  }
  // subtle noise
  const img = g.getImageData(0, 0, TW, TH);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 10;
    img.data[i] += n;
    img.data[i + 1] += n;
    img.data[i + 2] += n;
  }
  g.putImageData(img, 0, 0);
  const X = (m: number) => (m + MARGIN) * PX;
  const Y = (m: number) => (m + MARGIN) * PX;
  g.strokeStyle = "rgba(255,255,255,0.92)";
  g.lineWidth = 0.14 * PX;
  g.strokeRect(X(0), Y(0), L * PX, W * PX);
  g.beginPath();
  g.moveTo(X(L / 2), Y(0));
  g.lineTo(X(L / 2), Y(W));
  g.stroke();
  const circle = (cx: number, cy: number, r: number, a0 = 0, a1 = Math.PI * 2) => {
    g.beginPath();
    g.arc(X(cx), Y(cy), r * PX, a0, a1);
    g.stroke();
  };
  circle(L / 2, W / 2, 9.15);
  g.fillStyle = "white";
  const spot = (x: number, y: number) => {
    g.beginPath();
    g.arc(X(x), Y(y), 0.3 * PX, 0, Math.PI * 2);
    g.fill();
  };
  spot(L / 2, W / 2);
  for (const side of [0, 1]) {
    const gx = side ? L : 0;
    const dir = side ? -1 : 1;
    // penalty area 16.5 × 40.32, goal area 5.5 × 18.32
    g.strokeRect(X(side ? L - 16.5 : 0), Y(W / 2 - 20.16), 16.5 * PX, 40.32 * PX);
    g.strokeRect(X(side ? L - 5.5 : 0), Y(W / 2 - 9.16), 5.5 * PX, 18.32 * PX);
    spot(gx + dir * 11, W / 2);
    const a = Math.acos(5.5 / 9.15);
    if (side) circle(L - 11, W / 2, 9.15, Math.PI - a, Math.PI + a);
    else circle(11, W / 2, 9.15, -a, a);
    // corner arcs
    circle(gx, 0, 1, side ? Math.PI / 2 : 0, side ? Math.PI : Math.PI / 2);
    circle(gx, W, 1, side ? Math.PI : -Math.PI / 2, side ? (3 * Math.PI) / 2 : 0);
  }
  return c;
}

export function Pitch() {
  const tex = useMemo(() => {
    const t = new THREE.CanvasTexture(drawPitch());
    t.anisotropy = 8;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, []);
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} receiveShadow>
        <planeGeometry args={[L + MARGIN * 2, W + MARGIN * 2]} />
        <meshStandardMaterial map={tex} roughness={0.95} metalness={0} />
      </mesh>
      <Goal x={-L / 2} dir={-1} />
      <Goal x={L / 2} dir={1} />
      <mesh rotation-x={-Math.PI / 2} position-y={-0.02}>
        <planeGeometry args={[220, 170]} />
        <meshStandardMaterial color="#0b1220" roughness={1} />
      </mesh>
    </group>
  );
}

function Goal({ x, dir }: { x: number; dir: number }) {
  const post = new THREE.MeshStandardMaterial({ color: "#f8fafc", emissive: "#94a3b8", emissiveIntensity: 0.25 });
  const h = 2.44;
  const w = 7.32;
  const d = 2;
  return (
    <group position={[x, 0, 0]}>
      {[-w / 2, w / 2].map((z) => (
        <mesh key={z} position={[0, h / 2, z]} material={post} castShadow>
          <cylinderGeometry args={[0.07, 0.07, h, 10]} />
        </mesh>
      ))}
      <mesh position={[0, h, 0]} rotation-x={Math.PI / 2} material={post}>
        <cylinderGeometry args={[0.07, 0.07, w, 10]} />
      </mesh>
      <mesh position={[(dir * d) / 2, h / 2, 0]}>
        <boxGeometry args={[d, h, w]} />
        <meshBasicMaterial color="#e2e8f0" wireframe transparent opacity={0.18} />
      </mesh>
    </group>
  );
}

/** Procedural stands with an instanced crowd that subtly "breathes". */
export function Stadium({ home, away }: { home: string; away: string }) {
  const crowd = useRef<THREE.InstancedMesh>(null!);
  const { count, matrices, colors, phases } = useMemo(() => {
    const m: THREE.Matrix4[] = [];
    const cols: THREE.Color[] = [];
    const ph: number[] = [];
    const palette = [home, home, away, "#e2e8f0", "#334155", home, away, "#64748b"].map((c) => new THREE.Color(c));
    const o = new THREE.Object3D();
    const sides = [
      { len: L + 16, along: "x", offset: W / 2 + 11, sign: 1 },
      { len: L + 16, along: "x", offset: -(W / 2 + 11), sign: -1 },
      { len: W + 10, along: "z", offset: L / 2 + 11, sign: 1 },
      { len: W + 10, along: "z", offset: -(L / 2 + 11), sign: -1 },
    ];
    for (const s of sides) {
      for (let row = 0; row < 10; row++) {
        for (let i = 0; i < s.len / 1.1; i++) {
          if (Math.random() < 0.12) continue;
          const t = -s.len / 2 + i * 1.1 + Math.random() * 0.2;
          const depth = s.offset + s.sign * row * 1.5;
          const y = 1.2 + row * 1.1;
          if (s.along === "x") o.position.set(t, y, depth);
          else o.position.set(depth, y, t);
          o.updateMatrix();
          m.push(o.matrix.clone());
          cols.push(palette[Math.floor(Math.random() * palette.length)]);
          ph.push(Math.random() * Math.PI * 2);
        }
      }
    }
    return { count: m.length, matrices: m, colors: cols, phases: ph };
  }, [home, away]);

  const init = useRef(false);
  const frame = useRef(0);
  useFrame(({ clock }) => {
    const mesh = crowd.current;
    if (!mesh) return;
    frame.current++;
    if (!init.current) {
      matrices.forEach((mx, i) => {
        mesh.setMatrixAt(i, mx);
        mesh.setColorAt(i, colors[i]);
      });
      mesh.instanceColor!.needsUpdate = true;
      init.current = true;
    }
    // gentle bob for a fraction of the crowd, a few times per second (keeps GPU uploads tiny)
    if (frame.current % 8 !== 0) return;
    const t = clock.elapsedTime;
    const o = new THREE.Object3D();
    for (let k = 0; k < 250; k++) {
      const i = Math.floor(Math.random() * count);
      o.matrix.copy(matrices[i]);
      o.matrix.decompose(o.position, o.quaternion, o.scale);
      o.position.y += Math.max(0, Math.sin(t * 3 + phases[i])) * 0.12;
      o.updateMatrix();
      mesh.setMatrixAt(i, o.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  });

  return (
    <group>
      <instancedMesh ref={crowd} args={[undefined, undefined, count]}>
        <boxGeometry args={[0.55, 0.7, 0.45]} />
        <meshStandardMaterial roughness={0.8} />
      </instancedMesh>
      {/* tiers */}
      {[
        [0, W / 2 + 18, L + 20, 16, 0],
        [0, -(W / 2 + 18), L + 20, 16, 0],
        [L / 2 + 18, 0, 16, W + 14, 0],
        [-(L / 2 + 18), 0, 16, W + 14, 0],
      ].map(([x, z, w, d], i) => (
        <mesh key={i} position={[x, 5.5, z]} rotation-x={0}>
          <boxGeometry args={[w, 0.4, d]} />
          <meshStandardMaterial color="#0f172a" />
        </mesh>
      ))}
      {/* roof rims glowing */}
      {[
        [0, 19, W / 2 + 26, L + 30, 1],
        [0, 19, -(W / 2 + 26), L + 30, 1],
      ].map(([x, y, z, w], i) => (
        <mesh key={i} position={[x, y, z]}>
          <boxGeometry args={[w, 0.4, 10]} />
          <meshStandardMaterial color="#0b1220" emissive="#22d3ee" emissiveIntensity={0.08} />
        </mesh>
      ))}
      {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sz], i) => (
        <group key={i} position={[sx * (L / 2 + 22), 0, sz * (W / 2 + 22)]}>
          <mesh position={[0, 16, 0]}>
            <cylinderGeometry args={[0.4, 0.6, 32, 8]} />
            <meshStandardMaterial color="#1e293b" />
          </mesh>
          <mesh position={[0, 32.5, 0]}>
            <boxGeometry args={[6, 3, 1]} />
            <meshStandardMaterial color="#f8fafc" emissive="#f8fafc" emissiveIntensity={2.2} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
