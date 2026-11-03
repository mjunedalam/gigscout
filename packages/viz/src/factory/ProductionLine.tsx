import { type CSSProperties, useEffect, useRef } from "react";

import type { CockpitModel } from "../cockpit/model";
import { usePrefersReducedMotion } from "../useSize";
import { FactoryEngine } from "./engine";
import { LABEL_CSS } from "./labels";

export interface ProductionLineProps {
  model: CockpitModel;
  /** Changes when a different run is shown, so the floor clears and the stations build up again. */
  runKey: string | null;
  follow: boolean;
  dark: boolean;
  style?: CSSProperties;
}

const STYLE_ID = "gsf-styles";

function ensureStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = LABEL_CSS;
  document.head.appendChild(style);
}

/**
 * The agent production line: stations rise when their step starts, lead cards ride a conveyor through a
 * scanning gate into a reject bin or the shortlist, and the best become pitches. Lazy-load this entry
 * ("@gigscout/viz/factory"): it pulls in three.js.
 */
export default function ProductionLine({ model, runKey, follow, dark, style }: ProductionLineProps) {
  const host = useRef<HTMLDivElement>(null);
  const engine = useRef<FactoryEngine | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    ensureStyles();
    engine.current = new FactoryEngine(host.current!, dark);
    return () => {
      engine.current?.dispose();
      engine.current = null;
    };
    // the engine lives as long as the component; theme and data flow in through the effects below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => engine.current?.setDark(dark), [dark]);
  useEffect(() => engine.current?.setFollow(follow), [follow]);
  useEffect(() => engine.current?.setReducedMotion(reducedMotion), [reducedMotion]);
  useEffect(() => engine.current?.resetRun(), [runKey]);
  useEffect(() => engine.current?.setModel(model), [model]);

  return (
    <div
      ref={host}
      role="img"
      aria-label="Live production line of the agents working on this run"
      style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", ...style }}
    />
  );
}
