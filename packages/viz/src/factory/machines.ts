import { ConeGeometry, CylinderGeometry, DoubleSide, Group, type Mesh, SphereGeometry, TorusGeometry } from "three";

import { BELT, type StationKind } from "./layout";
import { box, type Materials, mesh } from "./materials";

/** Parts that move while a station works. */
export interface MachineParts {
  spin?: Group;
  scan?: Mesh;
  needle?: Group;
  paddle?: Group;
  roller?: Mesh;
  sheet?: Mesh;
  bars?: Mesh[];
}

/** One silhouette per job: a planning desk, a scanning mast, a sorting gate, a press, a growing chart. */
export function machine(kind: StationKind, color: string, M: Materials): { group: Group; parts: MachineParts } {
  const g = new Group();
  const A = M.accent(color);
  const parts: MachineParts = {};
  const builders: Record<StationKind, () => void> = {
    brief: () => {
      g.add(mesh(box(2.3, 0.1, 1.4, 0.04), M.body, 0, 0.98, -1.5));
      for (const [x, z] of [[-1, -2.1], [1, -2.1], [-1, -0.9], [1, -0.9]] as const) g.add(mesh(box(0.09, 0.8, 0.09, 0.02), M.dark, x, 0.6, z));
      parts.sheet = mesh(box(1.5, 0.02, 0.95, 0.01), A, -0.1, 1.05, -1.5);
      g.add(parts.sheet);
      for (let i = 0; i < 4; i++) g.add(mesh(box(1.0 - (i % 2) * 0.35, 0.012, 0.05, 0.005), M.body, -0.25, 1.07, -1.85 + i * 0.22));
      const arm = mesh(new CylinderGeometry(0.03, 0.03, 0.9, 8), M.dark, 0.95, 1.45, -1.95);
      arm.rotation.z = -0.35;
      g.add(arm, mesh(new ConeGeometry(0.22, 0.28, 20, 1, true), M.dark, 0.72, 1.86, -1.85));
    },
    prospector: () => {
      g.add(mesh(new CylinderGeometry(0.2, 0.28, 1.7, 24), M.body, 0, 1.05, -1.6));
      const head = new Group();
      head.position.set(0, 2.05, -1.6);
      const dish = mesh(new SphereGeometry(0.75, 36, 10, 0, Math.PI * 2, 0, 0.62), A.clone());
      (dish.material as typeof A).side = DoubleSide;
      dish.rotation.x = Math.PI - Math.PI / 3.2;
      dish.position.set(0, 0.35, 0.1);
      head.add(dish, mesh(new TorusGeometry(0.62, 0.035, 10, 48), M.dark, 0, 0.62, 0.42).rotateX(-Math.PI / 3.2));
      g.add(head, mesh(box(0.34, 0.24, 2.9, 0.06), M.body, 0, 1.42, -0.25));
      const hopper = mesh(new CylinderGeometry(0.42, 0.2, 0.45, 4, 1, true), M.dark, 0, 1.1, BELT.z);
      hopper.rotation.y = Math.PI / 4;
      g.add(hopper);
      parts.spin = head;
    },
    qualifier: () => {
      for (const z of [BELT.z - 0.98, BELT.z + 0.98]) g.add(mesh(box(0.26, 1.75, 0.26, 0.05), M.body, 0, 0.88, z));
      g.add(mesh(box(0.42, 0.32, 2.3, 0.07), M.body, 0, 1.82, BELT.z));
      parts.scan = mesh(box(0.06, 0.05, 1.7, 0.02), A, 0, 1.3, BELT.z);
      g.add(parts.scan, mesh(box(1.7, 1.05, 1.0, 0.08), M.body, 0, 0.72, -1.7));
      g.add(mesh(new CylinderGeometry(0.3, 0.3, 0.04, 32), M.dark, 0, 0.82, -1.18).rotateX(Math.PI / 2));
      parts.needle = new Group();
      parts.needle.position.set(0, 0.82, -1.15);
      parts.needle.add(mesh(box(0.035, 0.25, 0.02, 0.01), A, 0, 0.11, 0));
      parts.paddle = new Group();
      parts.paddle.position.set(0.55, 0.5, BELT.z - 0.62);
      parts.paddle.add(mesh(box(1.0, 0.24, 0.05, 0.02), M.dark, -0.5, 0, 0));
      g.add(parts.needle, parts.paddle, mesh(box(0.8, 0.06, 0.02, 0.01), A, 0, 1.12, -1.19));
    },
    writer: () => {
      g.add(mesh(box(2.0, 1.15, 1.2, 0.08), M.body, 0, 0.78, -1.7));
      for (const z of [BELT.z - 0.95, BELT.z + 0.95]) g.add(mesh(box(1.3, 1.25, 0.14, 0.04), M.body, 0, 0.82, z));
      g.add(mesh(box(1.42, 0.34, 2.1, 0.07), M.body, 0, 1.55, BELT.z), mesh(box(1.1, 0.06, 0.02, 0.01), A, 0, 1.55, BELT.z + 1.06));
      parts.roller = mesh(new CylinderGeometry(0.2, 0.2, 1.8, 24), M.dark, 0, 1.88, BELT.z);
      parts.roller.rotation.x = Math.PI / 2;
      g.add(parts.roller, mesh(box(0.7, 0.42, 0.04, 0.02), M.dark, -0.4, 1.0, -1.09));
    },
    report: () => {
      const board = mesh(box(2.2, 1.45, 0.09, 0.04), M.body, 0, 1.55, -1.75);
      board.rotation.x = -0.12;
      g.add(board);
      for (const x of [-0.8, 0.8]) g.add(mesh(box(0.08, 1.4, 0.08, 0.02), M.dark, x, 0.75, -1.65));
      parts.bars = [0.45, 0.8, 1.1].map((h, i) => {
        const geo = box(0.32, 1, 0.06, 0.02);
        geo.translate(0, 0.5, 0);
        const bar = mesh(geo, A, -0.55 + i * 0.55, 0.95, -1.66);
        bar.rotation.x = -0.12;
        bar.userData.h = h;
        g.add(bar);
        return bar;
      });
    },
  };
  builders[kind]();
  return { group: g, parts };
}

/** Station shell: platform, accent stripe, a glass gauge that fills with progress, and a status lamp. */
export function shell(color: string, M: Materials) {
  const rise = new Group();
  rise.add(mesh(box(3.6, 0.22, 2.8, 0.08), M.plat, 0, 0.11, -1.45), mesh(box(3.2, 0.07, 0.05, 0.02), M.accent(color), 0, 0.15, -0.04));
  const tube = new Group();
  tube.position.set(-1.45, 0.22, -2.45);
  tube.add(mesh(new CylinderGeometry(0.2, 0.2, 1.9, 24, 1, true), M.glass, 0, 0.95, 0));
  for (const y of [0, 1.9]) tube.add(mesh(new CylinderGeometry(0.24, 0.24, 0.06, 24), M.dark, 0, y, 0));
  const fluidGeo = new CylinderGeometry(0.16, 0.16, 1.84, 24);
  fluidGeo.translate(0, 0.92, 0);
  const fluid = mesh(fluidGeo, M.accent(color), 0, 0.03, 0);
  fluid.scale.y = 0.001;
  tube.add(fluid);
  const lamp = mesh(new CylinderGeometry(0.11, 0.11, 0.08, 20), M.dark.clone(), 1.5, 0.26, -0.3);
  rise.add(tube, lamp);
  return { rise, fluid, lamp };
}

/** Head of Sales' control booth at the back of the line. */
export function booth(color: string, M: Materials): Group {
  const g = new Group();
  g.add(
    mesh(box(2.4, 0.22, 1.3, 0.08), M.plat, 0, 0.11, 0),
    mesh(new CylinderGeometry(0.24, 0.3, 1.7, 24), M.body, 0, 1.05, 0),
    mesh(box(1.9, 0.8, 1.15, 0.12), M.body, 0, 2.25, 0),
    mesh(box(1.92, 0.26, 1.17, 0.05), M.dark, 0, 2.32, 0),
    mesh(box(2.0, 0.09, 1.25, 0.04), M.accent(color), 0, 2.7, 0),
    mesh(new CylinderGeometry(0.02, 0.02, 0.7, 8), M.dark, 0.6, 3.05, -0.2),
  );
  return g;
}

/** An open tray on the floor (rejects, shortlist, finished pitches). */
export function tray(mat: Materials["bin"], w = 1.5, d = 1.05): Group {
  const g = new Group();
  g.add(mesh(box(w, 0.06, d, 0.02), mat, 0, 0.03, 0));
  for (const [dx, dz, ww, dd] of [[0, -d / 2, w, 0.06], [0, d / 2, w, 0.06], [-w / 2, 0, 0.06, d], [w / 2, 0, 0.06, d]] as const) {
    g.add(mesh(box(ww, 0.32, dd, 0.02), mat, dx, 0.16, dz));
  }
  return g;
}

