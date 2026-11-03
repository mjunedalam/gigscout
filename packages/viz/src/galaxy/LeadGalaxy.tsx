import type { MapPoint } from "@gigscout/api-client";
import { Html, OrbitControls, Stars } from "@react-three/drei";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { AdditiveBlending, Color, type InstancedMesh, Object3D } from "three";

import { KIND_COLORS, KIND_LABELS } from "../palette";
import { usePrefersReducedMotion } from "../useSize";

const SPREAD = 1.45;
const BASE_SIZE = 0.022;
const SCORE_SIZE = 0.045;
const HALO_SCALE = 2.6;

export interface LeadGalaxyProps {
  points: MapPoint[];
  height?: number;
  onSelect?: (id: string) => void;
}

/**
 * Every lead as a star, placed by meaning: the API projects each lead's embedding to 3D (PCA), so leads about
 * similar work cluster together. Colour = lead kind, size and glow = qualification score.
 */
export default function LeadGalaxy({ points, height = 420, onSelect }: LeadGalaxyProps) {
  const reducedMotion = usePrefersReducedMotion();
  return (
    <div style={{ height, position: "relative" }} className="gs-galaxy" aria-label="3D map of leads clustered by meaning">
      <Canvas camera={{ position: [0, 0.4, 3.4], fov: 48 }} dpr={[1, 2]} gl={{ alpha: true, antialias: true }}>
        <ambientLight intensity={0.7} />
        <pointLight position={[3, 3, 4]} intensity={40} />
        <Stars radius={40} depth={25} count={900} factor={2.2} fade speed={reducedMotion ? 0 : 0.4} />
        <Constellation points={points} onSelect={onSelect} />
        <OrbitControls
          enablePan={false}
          autoRotate={!reducedMotion}
          autoRotateSpeed={0.5}
          minDistance={1.6}
          maxDistance={7}
          enableDamping
        />
      </Canvas>
    </div>
  );
}

function Constellation({ points, onSelect }: Pick<LeadGalaxyProps, "points" | "onSelect">) {
  const stars = useRef<InstancedMesh>(null);
  const halos = useRef<InstancedMesh>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const colors = useMemo(() => points.map((p) => new Color(KIND_COLORS[p.kind])), [points]);

  useLayoutEffect(() => {
    const dummy = new Object3D();
    points.forEach((p, i) => {
      const size = BASE_SIZE + (p.score ?? 0.15) * SCORE_SIZE;
      dummy.position.set(p.x * SPREAD, p.y * SPREAD, p.z * SPREAD);
      dummy.scale.setScalar(size * (i === hovered ? 1.8 : 1));
      dummy.updateMatrix();
      stars.current?.setMatrixAt(i, dummy.matrix);
      stars.current?.setColorAt(i, colors[i]!);
      dummy.scale.setScalar(size * HALO_SCALE * (i === hovered ? 1.6 : 1));
      dummy.updateMatrix();
      halos.current?.setMatrixAt(i, dummy.matrix);
      halos.current?.setColorAt(i, colors[i]!);
    });
    for (const mesh of [stars.current, halos.current]) {
      if (!mesh) continue;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }, [points, colors, hovered]);

  const active = hovered === null ? undefined : points[hovered];
  const onMove = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    setHovered(event.instanceId ?? null);
    document.body.style.cursor = "pointer";
  };
  const onOut = () => {
    setHovered(null);
    document.body.style.cursor = "";
  };

  if (!points.length) return null;
  return (
    <group>
      <instancedMesh
        ref={stars}
        args={[undefined, undefined, points.length]}
        onPointerMove={onMove}
        onPointerOut={onOut}
        onClick={(e) => e.instanceId !== undefined && onSelect?.(points[e.instanceId]!.id)}
      >
        <sphereGeometry args={[1, 16, 16]} />
        <meshStandardMaterial roughness={0.35} metalness={0.1} emissiveIntensity={0.4} />
      </instancedMesh>
      <instancedMesh ref={halos} args={[undefined, undefined, points.length]} raycast={() => null}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshBasicMaterial transparent opacity={0.16} blending={AdditiveBlending} depthWrite={false} />
      </instancedMesh>
      {active && (
        <Html position={[active.x * SPREAD, active.y * SPREAD, active.z * SPREAD]} distanceFactor={undefined}>
          <div className="gs-tooltip gs-galaxy-tip">
            <strong>{active.title}</strong>
            <div className="gs-tooltip-row">
              <span className="gs-dot" style={{ background: KIND_COLORS[active.kind] }} />
              {KIND_LABELS[active.kind]} · {active.source}
              {active.score !== null && <b>{active.score.toFixed(2)}</b>}
            </div>
          </div>
        </Html>
      )}
    </group>
  );
}
