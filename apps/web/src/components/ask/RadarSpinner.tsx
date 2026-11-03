/**
 * GigScout's "working" glyph: a radar sweeping for leads. Spins while active, rests as a still mark otherwise.
 * Plays the role Claude Code's ✻ and Codex's spinner do, in our own visual language.
 */
export function RadarSpinner({ size = 16, active = true }: { size?: number; active?: boolean }) {
  return (
    <svg
      className={`gs-radar${active ? " is-active" : ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      role="img"
      aria-label={active ? "Working" : "GigScout"}
    >
      <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="5.5" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="1.2" />
      <g className="gs-radar-sweep">
        <path d="M12 12 L12 2 A10 10 0 0 1 20.66 7 Z" fill="currentColor" fillOpacity="0.32" />
        <line x1="12" y1="12" x2="12" y2="2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </g>
      <circle className="gs-radar-blip" cx="16.4" cy="7.6" r="1.6" fill="currentColor" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    </svg>
  );
}
