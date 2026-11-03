import { CapsuleGeometry, CylinderGeometry, Group, type Mesh, SphereGeometry } from "three";

import { AGENT_COLORS } from "./layout";
import { box, type Materials, mesh } from "./materials";

/** Deck height of the mezzanine the Head of Sales works from. */
export const HQ_DECK = 3.1; // high enough that the board clears the stations' callouts
export const HQ_SCALE = 1.2;
/** Top of the pipeline board, where its callout dot sits. */
export const HQ_TOP = (HQ_DECK + 2.2) * HQ_SCALE;

export interface HqParts {
  /** Turns to face the station being directed. */
  head: Group;
  /** Leans in while the Head of Sales is busy with its own step (planning, the briefing). */
  torso: Group;
  /** The pipeline board: found, reviewed, qualified, pitched. */
  bars: Mesh[];
}

/**
 * The Head of Sales' control room: a mezzanine overlooking the line, with the only human figure on the floor
 * (every specialist is a machine) and the one view a sales manager watches, the pipeline board.
 */
export function headquarters(M: Materials): { group: Group; parts: HqParts } {
  const g = new Group();
  const gold = M.accent(AGENT_COLORS.head);
  const D = HQ_DECK;

  // mezzanine: slim columns, deck, gold fascia, front railing
  for (const [x, z] of [[-2.35, -0.85], [2.35, -0.85], [-2.35, 0.85], [2.35, 0.85]] as const) {
    g.add(mesh(new CylinderGeometry(0.08, 0.1, D, 16), M.rail, x, D / 2, z));
  }
  g.add(mesh(box(5.3, 0.18, 2.3, 0.06), M.plat, 0, D, 0), mesh(box(5.3, 0.12, 0.06, 0.02), gold, 0, D - 0.03, 1.16));
  for (let x = -2.4; x <= 2.41; x += 0.6) g.add(mesh(new CylinderGeometry(0.022, 0.022, 0.5, 8), M.dark, x, D + 0.34, 1.02));
  g.add(mesh(box(5.0, 0.04, 0.06, 0.02), M.dark, 0, D + 0.6, 1.02));
  // stairs down the right side, so it reads as a place people work, not a prop
  const steps = Math.round((D - 0.2) / 0.38);
  for (let i = 0; i < steps; i++) g.add(mesh(box(0.7, 0.06, 0.32, 0.02), M.body, 2.95, D - 0.2 - i * 0.38, 0.75 - i * 0.24));

  // desk with a laptop, chair, and the figure facing the line
  g.add(mesh(box(1.9, 0.08, 0.72, 0.03), M.body, 0, D + 0.7, 0.25), mesh(box(1.8, 0.52, 0.06, 0.02), M.body, 0, D + 0.4, 0.58));
  g.add(mesh(box(0.5, 0.02, 0.34, 0.01), M.dark, 0.45, D + 0.75, 0.22), mesh(box(0.5, 0.3, 0.02, 0.01), M.dark, 0.45, D + 0.9, 0.06));
  g.add(mesh(box(0.6, 0.62, 0.08, 0.03), M.dark, 0, D + 0.55, -0.55));
  const torso = new Group();
  torso.position.set(0, D + 0.09, -0.3);
  torso.add(mesh(new CapsuleGeometry(0.22, 0.46, 6, 16), gold, 0, 0.58, 0));
  const head = new Group();
  head.position.set(0, 1.14, 0);
  head.add(mesh(new SphereGeometry(0.17, 24, 16), M.body), mesh(box(0.2, 0.05, 0.05, 0.02), M.dark, 0, 0.02, 0.15));
  torso.add(head);
  g.add(torso);

  // pipeline board behind the desk: four bars that grow with the run
  g.add(mesh(box(2.9, 1.65, 0.1, 0.05), M.dark, 0, D + 1.38, -0.98));
  const colors = [AGENT_COLORS.prospector, AGENT_COLORS.qualifier, AGENT_COLORS.writer, AGENT_COLORS.head];
  const bars = colors.map((c, i) => {
    const geo = box(0.42, 1, 0.04, 0.02);
    geo.translate(0, 0.5, 0);
    const bar = mesh(geo, M.accent(c), -0.93 + i * 0.62, D + 0.7, -0.91);
    bar.scale.y = 0.02;
    g.add(bar);
    return bar;
  });
  g.scale.setScalar(HQ_SCALE);
  return { group: g, parts: { head, torso, bars } };
}
