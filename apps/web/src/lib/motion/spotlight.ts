/*
 * Cursor spotlight: one delegated pointer listener feeds --mx / --my to whichever panel is under the cursor,
 * and CSS paints a soft glow at that point. One listener for the whole app, throttled to animation frames.
 */
const TARGET = ".gs-panel, .gs-spot";

export function installSpotlight(): () => void {
  if (typeof window === "undefined" || window.matchMedia?.("(hover: none)").matches) return () => {};
  let frame = 0;
  let last: PointerEvent | null = null;

  const paint = () => {
    frame = 0;
    if (!last) return;
    const el = (last.target as Element | null)?.closest?.(TARGET) as HTMLElement | null;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${last.clientX - rect.left}px`);
    el.style.setProperty("--my", `${last.clientY - rect.top}px`);
  };

  const onMove = (event: PointerEvent) => {
    last = event;
    if (!frame) frame = requestAnimationFrame(paint);
  };

  window.addEventListener("pointermove", onMove, { passive: true });
  return () => {
    window.removeEventListener("pointermove", onMove);
    if (frame) cancelAnimationFrame(frame);
  };
}
