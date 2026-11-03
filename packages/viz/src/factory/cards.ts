import { type Material, Mesh, MeshStandardMaterial, type Scene, Vector3 } from "three";

import { type CockpitLead, type CockpitModel, NOT_A_MATCH } from "../cockpit/model";
import { BELT, TRAYS, X } from "./layout";
import { box } from "./materials";

/**
 * Every lead is a card that follows a real route: chute → belt → queue → scanning gate → reject bin or shortlist
 * tray → back onto the belt → press → pitches tray. Cards react to the model (found / reviewed / pitched) and
 * move at belt speed, so what you see is what the agents did, in order.
 */
const SPEED = 3.2;
const MAX_CARDS = 160; // beyond this the counts still tell the story; the line stays readable
const QHEAD = X[2] - 1.05, QGAP = 0.7, QSLOTS = 5;
const GATE_BURST_SECONDS = 2.5; // a burst of reviews streams through the gate in about this long

type Phase =
  | "hidden" | "drop" | "queue" | "gate" | "toBin" | "inBin" | "toShort" | "toTray" | "inTray"
  | "fromTray" | "toWriter" | "press" | "toOut" | "toOutTray" | "inOut";
interface Leg { kind: "ride" | "hop" | "drop" | "wait"; from: Vector3; to: Vector3; dur: number; h: number }
interface StepContext { qRank: number; isNext: boolean; gap: number; trayRank: Map<string, number>; trayCount: number }
interface Card { id: string; mesh: Mesh; phase: Phase; leg: Leg | null; legT: number; shortIdx: number }

const onBelt = (x: number) => new Vector3(x, BELT.y, BELT.z);
const smooth = (k: number) => k * k * (3 - 2 * k);
const leg = (kind: Leg["kind"], from: Vector3, to: Vector3, dur: number, h = 0): Leg => ({ kind, from: from.clone(), to: to.clone(), dur: Math.max(dur, 0.05), h });
const ride = (from: Vector3, toX: number) => leg("ride", from, onBelt(toX), Math.abs(toX - from.x) / SPEED);
const hop = (from: Vector3, to: Vector3, h = 0.8, dur = 0.42) => leg("hop", from, to, dur, h);
const binSlot = (i: number) => new Vector3(TRAYS.bin.x - 0.45 + (i % 3) * 0.45, 0.1 + Math.floor(i / 6) * 0.042, TRAYS.bin.z - 0.22 + (Math.floor(i / 3) % 2) * 0.44);
const shortSlot = (i: number) => new Vector3(TRAYS.shortlist.x, 0.1 + i * 0.046, TRAYS.shortlist.z);
const outSlot = (i: number) => new Vector3(TRAYS.pitches.x - 0.15 + (i % 2) * 0.08, 0.1 + i * 0.075, TRAYS.pitches.z);

function legPos(L: Leg, k: number, out: Vector3) {
  if (L.kind === "drop") return out.lerpVectors(L.from, L.to, k * k);
  if (L.kind === "hop") {
    out.lerpVectors(L.from, L.to, smooth(k));
    out.y += Math.sin(Math.PI * k) * L.h;
    return out;
  }
  return out.lerpVectors(L.from, L.to, k);
}

export class CardFlow {
  private readonly geo = box(0.62, 0.04, 0.44, 0.016);
  private readonly mats = {
    found: new MeshStandardMaterial({ color: 0xe7f3ea, roughness: 0.7 }),
    qual: new MeshStandardMaterial({ color: 0xdbe6fb, roughness: 0.7 }),
    rej: new MeshStandardMaterial({ color: 0xc8ccd3, roughness: 0.8 }),
    env: new MeshStandardMaterial({ color: 0xe8ddf8, roughness: 0.65 }),
  };
  private cards = new Map<string, Card>();
  private tally = { bin: 0, short: 0, out: 0 };
  private gateFreeAt = 0;
  private clock = 0;

  constructor(private readonly scene: Scene) {}

  /** True while any card is riding the belt (the belt texture moves with them). */
  get beltMoving() {
    for (const c of this.cards.values()) if (c.leg?.kind === "ride") return true;
    return false;
  }

  /** Cards currently under the scanning gate / just kicked into the bin (drive the gate's animation). */
  get gateBusy() {
    for (const c of this.cards.values()) if (c.phase === "gate" && Math.abs(c.mesh.position.x - X[2]) < 0.5) return true;
    return false;
  }
  get kicking() {
    for (const c of this.cards.values()) if (c.phase === "toBin" && c.legT < 0.22) return true;
    return false;
  }

  reset() {
    this.cards.forEach((c) => this.scene.remove(c.mesh));
    this.cards.clear();
    this.tally = { bin: 0, short: 0, out: 0 };
    this.gateFreeAt = 0;
  }

  update(model: CockpitModel, dt: number) {
    this.clock += dt;
    for (const id of model.order.slice(0, MAX_CARDS)) {
      if (!this.cards.has(id)) this.cards.set(id, this.spawn(id, model.leads[id]!));
    }
    const queue = [...this.cards.values()].filter((c) => c.phase === "queue" || c.phase === "drop");
    const rank = new Map(queue.map((c, i) => [c.id, i]));
    const reviewedWaiting = queue.filter((c) => model.leads[c.id]!.reviewed).length;
    const gap = Math.min(Math.max(GATE_BURST_SECONDS / Math.max(reviewedWaiting, 1), 0.06), 0.3);
    const inTray = [...this.cards.values()].filter((c) => c.phase === "inTray").sort((a, b) => a.shortIdx - b.shortIdx);
    const trayRank = new Map(inTray.map((c, i) => [c.id, i]));
    // the Qualifier does not review in queue order: the first reviewed card in the queue goes through next
    const next = queue.find((c) => c.phase === "queue" && model.leads[c.id]!.reviewed && model.leads[c.id]!.reason !== NOT_A_MATCH)?.id;
    for (const c of this.cards.values()) {
      this.step(c, model.leads[c.id]!, dt, { qRank: rank.get(c.id) ?? 0, isNext: c.id === next, gap, trayRank, trayCount: inTray.length });
    }
  }

  dispose() {
    this.reset();
    this.geo.dispose();
    Object.values(this.mats).forEach((m) => m.dispose());
  }

  private spawn(id: string, lead: CockpitLead): Card {
    const mesh = new Mesh(this.geo, this.mats.found);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.rotation.y = ((hash(id) % 9) - 4) * 0.02;
    this.scene.add(mesh);
    const card: Card = { id, mesh, phase: "hidden", leg: null, legT: 0, shortIdx: 0 };
    if (lead.fromMemory) { mesh.position.copy(onBelt(QHEAD - QGAP * QSLOTS)); card.phase = "queue"; }
    else { mesh.position.set(X[1], 1.05, BELT.z); this.go(card, "drop", leg("drop", mesh.position, onBelt(X[1]), 0.24)); }
    return card;
  }

  private go(c: Card, phase: Phase, L: Leg | null) { c.phase = phase; c.leg = L; c.legT = 0; }

  private setMat(c: Card, m: Material) { c.mesh.material = m; }

  private step(c: Card, l: CockpitLead, dt: number, ctx: StepContext) {
    const { qRank, isNext, gap, trayRank, trayCount } = ctx;
    const pos = c.mesh.position;
    if (c.leg) {
      c.legT += dt;
      const k = Math.min(c.legT / c.leg.dur, 1);
      legPos(c.leg, k, pos);
      if (k < 1) return;
      c.leg = null;
      switch (c.phase) {
        case "drop": c.phase = "queue"; break;
        case "gate":
          if (l.qualified) { this.setMat(c, this.mats.qual); this.go(c, "toShort", ride(pos, TRAYS.shortlist.x)); }
          else { this.setMat(c, this.mats.rej); this.go(c, "toBin", hop(pos, binSlot(this.tally.bin++), 0.9, 0.45)); }
          return;
        case "toShort": c.shortIdx = this.tally.short++; this.go(c, "toTray", hop(pos, shortSlot(trayCount), 0.75, 0.36)); return;
        case "toTray": c.phase = "inTray"; break;
        case "toBin": c.phase = "inBin"; break;
        case "fromTray": this.go(c, "toWriter", ride(pos, X[3])); return;
        case "toWriter": this.go(c, "press", leg("wait", pos, pos, 0.45)); return;
        case "press": this.setMat(c, this.mats.env); c.mesh.scale.set(0.95, 2.2, 0.8); this.go(c, "toOut", ride(pos, TRAYS.pitches.x + 0.9)); return;
        case "toOut": this.go(c, "toOutTray", hop(pos, outSlot(this.tally.out++), 0.65, 0.38)); return;
        case "toOutTray": c.phase = "inOut"; break;
        default: break;
      }
    }
    if (c.phase === "queue") {
      if (l.reviewed && l.reason === NOT_A_MATCH) { // never scored: it leaves the queue straight for the bin
        this.setMat(c, this.mats.rej);
        this.go(c, "toBin", hop(pos, binSlot(this.tally.bin++), 0.7, 0.4 + Math.min(qRank, 20) * 0.02));
        return;
      }
      if (isNext && this.clock >= this.gateFreeAt) {
        this.gateFreeAt = this.clock + gap;
        this.go(c, "gate", ride(pos, X[2] + 0.35));
        return;
      }
      const tx = QHEAD - (qRank % QSLOTS) * QGAP, ty = BELT.y + Math.floor(qRank / QSLOTS) * 0.042;
      pos.x += Math.sign(tx - pos.x) * Math.min(Math.abs(tx - pos.x), SPEED * dt);
      pos.y += (ty - pos.y) * Math.min(dt * 12, 1);
      pos.z = BELT.z;
    }
    if (c.phase === "inTray") {
      if (l.pitched) { this.go(c, "fromTray", hop(pos, onBelt(TRAYS.shortlist.x + 0.4), 0.7, 0.38)); return; }
      pos.lerp(shortSlot(trayRank.get(c.id) ?? 0), Math.min(dt * 10, 1));
    }
  }
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}
