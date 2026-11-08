import { useLayoutEffect, useRef } from "react";

import { formatCount } from "./count";
import { MOTION, gsap, prefersReducedMotion } from "./gsap";

interface AnimatedNumberProps {
  value: number;
  format?: (value: number) => string;
  duration?: number;
}

/**
 * A number that counts from its previous value to the new one. It writes to the DOM directly inside the tween,
 * so a live counter ticking every second never re-renders React.
 */
export function AnimatedNumber({ value, format = formatCount, duration = MOTION.slow }: AnimatedNumberProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef(0);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) {
      shown.current = value;
      el.textContent = format(value);
      return;
    }
    const state = { v: shown.current };
    el.textContent = format(state.v); // before paint, so the final value never flashes ahead of the count
    const tween = gsap.to(state, {
      v: value,
      duration,
      ease: "power2.out",
      onUpdate: () => {
        shown.current = state.v;
        el.textContent = format(state.v);
      },
    });
    return () => {
      tween.kill();
    };
  }, [value, format, duration]);

  // The first paint shows the real value; the tween only rewrites the digits on its way there.
  return (
    <span ref={ref} className="gs-num">
      {format(value)}
    </span>
  );
}
