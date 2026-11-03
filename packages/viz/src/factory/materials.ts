import { Color, type BufferGeometry, Mesh, MeshStandardMaterial } from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

/** Matte, warm-neutral palette. No emissive or bloom: meaning comes from form and accent colour, not glow. */
const PALETTE = {
  light: { plat: 0xd9d4ca, body: 0xfaf8f4, dark: 0x2e333b, rail: 0x9aa1ab, groove: 0xd8d4cb, bin: 0x6b7280 },
  dark: { plat: 0x2f3542, body: 0x3a4150, dark: 0x14171d, rail: 0x6b7382, groove: 0x1c2029, bin: 0x4b5260 },
} as const;
type Slot = keyof typeof PALETTE.light;

export class Materials {
  readonly plat: MeshStandardMaterial;
  readonly body: MeshStandardMaterial;
  readonly dark: MeshStandardMaterial;
  readonly rail: MeshStandardMaterial;
  readonly groove: MeshStandardMaterial;
  readonly bin: MeshStandardMaterial;
  readonly glass = new MeshStandardMaterial({ color: 0xffffff, roughness: 0.08, transparent: true, opacity: 0.28, depthWrite: false });
  private readonly themed: [MeshStandardMaterial, Slot][] = [];
  private readonly accents = new Map<string, MeshStandardMaterial>();

  constructor(dark: boolean) {
    const make = (slot: Slot, roughness: number, metalness = 0) => {
      const m = new MeshStandardMaterial({ color: PALETTE.light[slot], roughness, metalness });
      this.themed.push([m, slot]);
      return m;
    };
    this.plat = make("plat", 0.85);
    this.body = make("body", 0.7);
    this.dark = make("dark", 0.55);
    this.rail = make("rail", 0.38, 0.75);
    this.groove = make("groove", 0.95);
    this.bin = make("bin", 0.7, 0.1);
    this.setDark(dark);
  }

  accent(hex: string): MeshStandardMaterial {
    let m = this.accents.get(hex);
    if (!m) {
      m = new MeshStandardMaterial({ color: new Color(hex), roughness: 0.55, metalness: 0.05 });
      this.accents.set(hex, m);
    }
    return m;
  }

  setDark(dark: boolean) {
    const p = dark ? PALETTE.dark : PALETTE.light;
    this.themed.forEach(([m, slot]) => m.color.set(p[slot]));
  }

  dispose() {
    [...this.themed.map(([m]) => m), ...this.accents.values(), this.glass].forEach((m) => m.dispose());
  }
}

export const box = (w: number, h: number, d: number, r = 0.05) =>
  new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2, h / 2, d / 2));

export function mesh(geo: BufferGeometry, mat: MeshStandardMaterial, x = 0, y = 0, z = 0): Mesh {
  const m = new Mesh(geo, mat);
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  return m;
}
