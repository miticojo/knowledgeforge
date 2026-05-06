"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import * as THREE from "three";

export interface ProjectionPoint {
  id: string;
  label: string;
  type: string;
  layer: string;
  x: number;
  y: number;
  z: number;
}

const LAYER_COLORS: Record<string, string> = {
  Strategy: "#d97706",
  Motivation: "#84cc16",
  Business: "#3b82f6",
  Application: "#f97316",
  Technology: "#10b981",
  Other: "#94a3b8",
};

function normalize(points: ProjectionPoint[]): { points: ProjectionPoint[]; scale: number } {
  if (points.length === 0) return { points: [], scale: 1 };
  const max = points.reduce(
    (m, p) => Math.max(m, Math.abs(p.x), Math.abs(p.y), Math.abs(p.z)),
    1e-6,
  );
  const scale = 5 / max;
  return {
    points: points.map((p) => ({ ...p, x: p.x * scale, y: p.y * scale, z: p.z * scale })),
    scale,
  };
}

function PointCloud({
  points,
  highlightIds,
  onHover,
  onClick,
}: {
  points: ProjectionPoint[];
  highlightIds: Set<string>;
  onHover: (p: ProjectionPoint | null) => void;
  onClick: (p: ProjectionPoint) => void;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);

  const colors = useMemo(() => {
    const tmpColor = new THREE.Color();
    const cols = new Float32Array(points.length * 3);
    points.forEach((p, i) => {
      const baseHex = LAYER_COLORS[p.layer] || LAYER_COLORS.Other;
      tmpColor.set(baseHex);
      if (highlightIds.size > 0 && !highlightIds.has(p.id)) {
        tmpColor.multiplyScalar(0.65);
      }
      cols[i * 3 + 0] = tmpColor.r;
      cols[i * 3 + 1] = tmpColor.g;
      cols[i * 3 + 2] = tmpColor.b;
    });
    return cols;
  }, [points, highlightIds]);

  // Wire instanceColor on the InstancedMesh imperatively — declaring it as a
  // child <instancedBufferAttribute attach="instanceColor"> doesn't actually
  // bind to mesh.instanceColor, so the shader falls back to the material's
  // base color (white * uniform, but vertexColors=true with no buffer renders
  // pitch black on dark backgrounds).
  // Set both per-instance matrix and color via the official InstancedMesh API
  // (setColorAt). This wires the InstancedBufferAttribute internally and is
  // the only path that survives across re-renders in r3f.
  useFrame(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    const tmp = new THREE.Color();
    points.forEach((p, i) => {
      dummy.position.set(p.x, p.y, p.z);
      const isHi = highlightIds.has(p.id);
      const s = highlightIds.size === 0 ? 0.18 : isHi ? 0.28 : 0.14;
      dummy.scale.setScalar(s);
      dummy.updateMatrix();
      meshRef.current!.setMatrixAt(i, dummy.matrix);
      tmp.fromArray(colors, i * 3);
      meshRef.current!.setColorAt(i, tmp);
    });
    meshRef.current.instanceMatrix.needsUpdate = true;
    if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, points.length]}
      onPointerOver={(e) => {
        e.stopPropagation();
        const idx = e.instanceId;
        if (idx != null) onHover(points[idx]);
      }}
      onPointerOut={() => onHover(null)}
      onClick={(e) => {
        const idx = e.instanceId;
        if (idx != null) onClick(points[idx]);
      }}
    >
      <sphereGeometry args={[1, 12, 12]} />
      {/* No vertexColors flag — instanceColor on the InstancedMesh is wired
          automatically by three.js for any material; setting vertexColors
          actually disables that path. */}
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

function QueryMarker({ x, y, z }: { x: number; y: number; z: number }) {
  return (
    <mesh position={[x, y, z]}>
      <boxGeometry args={[0.35, 0.35, 0.35]} />
      <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.4} />
    </mesh>
  );
}

function HighlightLines({
  query,
  hits,
}: {
  query: { x: number; y: number; z: number };
  hits: ProjectionPoint[];
}) {
  return (
    <>
      {hits.map((p) => {
        const geom = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(query.x, query.y, query.z),
          new THREE.Vector3(p.x, p.y, p.z),
        ]);
        return (
          <line key={p.id}>
            <primitive attach="geometry" object={geom} />
            <lineBasicMaterial color="#fbbf24" linewidth={1} transparent opacity={0.6} />
          </line>
        );
      })}
    </>
  );
}

export interface EmbeddingScatterProps {
  points: ProjectionPoint[];
  query?: { x: number; y: number; z: number } | null;
  highlightIds?: string[];
  onSelect?: (p: ProjectionPoint) => void;
}

export default function EmbeddingScatter({
  points,
  query,
  highlightIds = [],
  onSelect,
}: EmbeddingScatterProps) {
  const [hovered, setHovered] = useState<ProjectionPoint | null>(null);

  const { points: norm, scale } = useMemo(() => normalize(points), [points]);
  const normQuery = useMemo(() => {
    if (!query) return null;
    return { x: query.x * scale, y: query.y * scale, z: query.z * scale };
  }, [query, scale]);
  const highlightSet = useMemo(() => new Set(highlightIds), [highlightIds]);
  const highlightedPoints = useMemo(
    () => norm.filter((p) => highlightSet.has(p.id)),
    [norm, highlightSet],
  );

  return (
    <div className="relative h-full w-full bg-black/90 rounded-xl overflow-hidden">
      <Canvas camera={{ position: [10, 7, 10], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[10, 10, 5]} intensity={0.7} />
        <axesHelper args={[6]} />
        <PointCloud
          points={norm}
          highlightIds={highlightSet}
          onHover={setHovered}
          onClick={(p) => onSelect?.(p)}
        />
        {normQuery && <QueryMarker {...normQuery} />}
        {normQuery && highlightedPoints.length > 0 && (
          <HighlightLines query={normQuery} hits={highlightedPoints} />
        )}
        <OrbitControls enableDamping dampingFactor={0.1} />
        {hovered && (
          <Html position={[hovered.x, hovered.y + 0.4, hovered.z]} center distanceFactor={8}>
            <div className="px-2 py-1 rounded bg-black/90 border border-white/20 text-xs whitespace-nowrap text-white">
              <div className="font-semibold">{hovered.label}</div>
              <div className="opacity-70">{hovered.type} · {hovered.layer}</div>
            </div>
          </Html>
        )}
      </Canvas>
      <div className="absolute bottom-3 left-3 flex gap-3 text-xs text-white/80 bg-black/60 px-3 py-2 rounded-lg backdrop-blur">
        {Object.entries(LAYER_COLORS).map(([layer, color]) => (
          <div key={layer} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full" style={{ background: color }} />
            <span>{layer}</span>
          </div>
        ))}
        {query && (
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 bg-red-600" />
            <span>Query</span>
          </div>
        )}
      </div>
    </div>
  );
}
