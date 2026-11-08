import { type RefObject, useLayoutEffect } from "react";

import { MOTION, gsap, prefersReducedMotion } from "../lib/motion/gsap";

/**
 * Slides one highlight pill to whichever nav link is active, instead of each link painting its own background.
 * Size is set instantly; only the move (transform) is animated.
 */
export function useNavIndicator(
  container: RefObject<HTMLElement | null>,
  pill: RefObject<HTMLElement | null>,
  deps: readonly unknown[],
): void {
  useLayoutEffect(() => {
    const box = container.current;
    const marker = pill.current;
    if (!box || !marker) return;
    let placed = false;

    const place = () => {
      const active = box.querySelector<HTMLElement>("a[data-active]");
      if (!active) {
        gsap.to(marker, { autoAlpha: 0, duration: MOTION.fast });
        placed = false;
        return;
      }
      const outer = box.getBoundingClientRect();
      const inner = active.getBoundingClientRect();
      gsap.set(marker, { width: inner.width, height: inner.height, x: inner.left - outer.left });
      const target = { y: inner.top - outer.top, autoAlpha: 1 };
      if (!placed || prefersReducedMotion()) gsap.set(marker, target);
      else gsap.to(marker, { ...target, duration: 0.5, ease: "expo.out", overwrite: "auto" });
      placed = true;
    };

    place();
    const observer = new ResizeObserver(() => place());
    observer.observe(box);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- callers pass what moves the active link
  }, deps);
}
