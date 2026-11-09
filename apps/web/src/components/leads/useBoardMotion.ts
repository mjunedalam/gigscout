import { Flip } from "gsap/Flip";
import { type RefObject, useCallback, useLayoutEffect, useRef } from "react";

import { MOTION, gsap, prefersReducedMotion, useGSAP } from "../../lib/motion/gsap";

// Registered here, not in the shared motion module, so Flip only ships with the leads screen.
gsap.registerPlugin(Flip);

const CARD_SELECTOR = "[data-flip-id]";
const LANDED_CLASS = "gs-card-landed";

interface PendingMove {
  state: Flip.FlipState;
  id: string;
}

/**
 * Motion for the pipeline board. Cards stagger in on first paint. Call `captureMove(id)` just before a move:
 * it records where every card is, and after React re-renders the board the cards glide (FLIP) from those spots
 * to their new ones, and the moved card glows once where it landed.
 */
export function useBoardMotion(containerRef: RefObject<HTMLElement | null>, items: unknown): (id: string) => void {
  const pending = useRef<PendingMove | null>(null);

  useGSAP(
    () => {
      if (prefersReducedMotion()) return;
      gsap.fromTo(
        CARD_SELECTOR,
        { autoAlpha: 0, y: 12 },
        { autoAlpha: 1, y: 0, duration: MOTION.normal, stagger: 0.025, clearProps: "transform,opacity,visibility" },
      );
    },
    { scope: containerRef },
  );

  const captureMove = useCallback(
    (id: string) => {
      const root = containerRef.current;
      if (!root || prefersReducedMotion()) return;
      pending.current = { state: Flip.getState(root.querySelectorAll(CARD_SELECTOR)), id };
    },
    [containerRef],
  );

  useLayoutEffect(() => {
    const move = pending.current;
    const root = containerRef.current;
    if (!move || !root) return;
    const landed = root.querySelector<HTMLElement>(`[data-flip-id="${CSS.escape(move.id)}"]`);
    // The optimistic update may not have rendered yet; keep the snapshot until the card has really moved.
    if (!landed || !hasMoved(move.state, landed)) return;
    pending.current = null;
    const flip = Flip.from(move.state, {
      targets: root.querySelectorAll(CARD_SELECTOR),
      duration: MOTION.normal,
      ease: MOTION.ease,
      nested: true,
      onComplete: () => glow(landed),
    });
    return () => {
      flip.kill();
    };
  }, [items, containerRef]);

  return captureMove;
}

function hasMoved(state: Flip.FlipState, el: HTMLElement): boolean {
  const before = state.getElementState(el);
  if (!before) return true;
  const now = el.getBoundingClientRect();
  return Math.abs(before.bounds.left - now.left) > 1 || Math.abs(before.bounds.top - now.top) > 1;
}

function glow(el: HTMLElement): void {
  el.classList.add(LANDED_CLASS);
  el.addEventListener("animationend", () => el.classList.remove(LANDED_CLASS), { once: true });
}
