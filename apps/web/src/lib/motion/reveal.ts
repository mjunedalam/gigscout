/*
 * Scroll reveal for panels and tiles. Elements that enter the viewport in the same frame are revealed as one
 * staggered batch, so a page full of panels cascades in instead of popping. IntersectionObserver, no scroll handlers.
 */
import { type RefObject, useLayoutEffect } from "react";

import { MOTION, gsap, prefersReducedMotion } from "./gsap";

const PENDING = "pending";
const DONE = "done";
const ATTR = "data-reveal";

let observer: IntersectionObserver | null = null;
let queue: HTMLElement[] = [];
let frame = 0;

function flush() {
  frame = 0;
  const batch = queue;
  queue = [];
  gsap.fromTo(
    batch,
    { autoAlpha: 0, y: 18, scale: 0.985 },
    {
      autoAlpha: 1,
      y: 0,
      scale: 1,
      duration: MOTION.normal,
      stagger: MOTION.stagger,
      // hand transform back to CSS so hover lifts keep working
      clearProps: "transform,opacity,visibility",
      onComplete: () => batch.forEach((el) => el.setAttribute(ATTR, DONE)),
    },
  );
}

function getObserver(): IntersectionObserver {
  observer ??= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target as HTMLElement;
        observer?.unobserve(el);
        queue = [...queue, el];
      }
      if (queue.length && !frame) frame = requestAnimationFrame(flush);
    },
    { rootMargin: "0px 0px -6% 0px" },
  );
  return observer;
}

/** Fades and lifts the element in the first time it scrolls into view. */
export function useReveal(ref: RefObject<HTMLElement | null>, enabled = true): void {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
      el.setAttribute(ATTR, DONE);
      return;
    }
    el.setAttribute(ATTR, PENDING);
    const io = getObserver();
    io.observe(el);
    return () => {
      io.unobserve(el);
      queue = queue.filter((q) => q !== el);
    };
  }, [ref, enabled]);
}
