import type { MapPoint } from "@gigscout/api-client";
import { Center, Loader } from "@mantine/core";
import { Component, lazy, type ReactNode, Suspense } from "react";

import { FlatGalaxy } from "./FlatGalaxy";
import { canUseWebGL } from "./webgl";

const LeadGalaxy = lazy(() => import("@gigscout/viz/galaxy"));

interface GalaxyProps {
  points: MapPoint[];
  height: number;
  onSelect: (id: string) => void;
}

interface BoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

/** Catches a WebGL failure (lost or refused context) so it costs the 3D view, never the whole page. */
class GalaxyBoundary extends Component<BoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.warn("Lead galaxy fell back to 2D:", error);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/** The 3D lead galaxy when the browser can draw it, otherwise the flat map. */
export function SafeGalaxy(props: GalaxyProps) {
  const flat = <FlatGalaxy {...props} />;
  if (!canUseWebGL()) return flat;
  return (
    <GalaxyBoundary fallback={flat}>
      <Suspense fallback={<Center h={props.height}><Loader type="dots" /></Center>}>
        <LeadGalaxy {...props} />
      </Suspense>
    </GalaxyBoundary>
  );
}
