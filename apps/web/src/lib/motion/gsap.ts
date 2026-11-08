/*
 * One place that owns GSAP: plugin registration, the shared motion vocabulary, and the reduced-motion switch.
 * Everything animates transform / opacity only, so motion stays on the compositor.
 */
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

gsap.registerPlugin(useGSAP);

export const MOTION = {
  fast: 0.25,
  normal: 0.6,
  slow: 1.1,
  stagger: 0.06,
  ease: "expo.out",
  easeSoft: "power3.out",
} as const;

gsap.defaults({ ease: MOTION.ease, duration: MOTION.normal });

const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

/** True when the viewer asked for less motion, or the environment cannot animate (tests, SSR). */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return true;
  if (import.meta.env.MODE === "test") return true;
  return window.matchMedia?.(REDUCED_QUERY).matches ?? false;
}

export { gsap, useGSAP };
