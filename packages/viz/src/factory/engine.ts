import type { RunStage } from "@gigscout/api-client";
import {
  ACESFilmicToneMapping, BoxGeometry, BufferGeometry, CanvasTexture, Color, CylinderGeometry, DirectionalLight, Group,
  HemisphereLight, Line, LineDashedMaterial, MathUtils, Mesh, MeshBasicMaterial, MeshStandardMaterial, OrthographicCamera, PCFSoftShadowMap, PlaneGeometry,
  PMREMGenerator, RepeatWrapping, Scene, ShadowMaterial, SpotLight, SRGBColorSpace, Vector3, WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";

import { type CockpitModel, isThinking, pileCounts, stageElapsed, stageProgress, stageState } from "../cockpit/model";
import { CardFlow } from "./cards";
import { boothCallout, drawSpark, type StationCallout, stationCallout, type TagCallout, tagCallout } from "./labels";
import { headquarters, HQ_DECK, HQ_SCALE, HQ_TOP, type HqParts } from "./headquarters";
import { AGENT_COLORS, BELT, BOUNDS, GROOVE_Z, HQ, STATIONS, TRAYS, X } from "./layout";
import { machine, type MachineParts, shell, tray } from "./machines";
import { box, Materials, mesh } from "./materials";

const VIEW_DIR = new Vector3(0.24, 1.3, 1).normalize();
const LOOK = new Vector3(0, 0.4, 0.5);
const FOLLOW_ZOOM = 1.55;
const SPARK_EVERY = 0.25;
const LAMP_PENDING = 0x9aa1ab, LAMP_DONE = 0x1f9d55;
const HQ_RISE_FROM = -7;
const HEAD_STAGES = new Set<RunStage>(["plan", "report"]);
const STAGE_VERB: Record<RunStage, string> = { plan: "planning the run", search: "directing search", qualify: "directing qualify", write: "directing outreach", report: "writing the briefing" };

interface BuiltStation {
  born: number;
  root: Group;
  rise: Group;
  hatch: Mesh;
  fluid: Mesh;
  lamp: Mesh;
  parts: MachineParts;
  callout: StationCallout;
  history: number[];
  history2: number[];
}

const easeBack = (p: number) => 1 + 2.2 * Math.pow(p - 1, 3) + 1.2 * Math.pow(p - 1, 2);

/**
 * The agent production line. Imperative three.js for a steady 60fps: React hands it the latest cockpit model
 * and it animates toward it every frame. Stations rise out of the floor when their step first starts.
 */
export class FactoryEngine {
  private readonly renderer = new WebGLRenderer({ antialias: true, alpha: true });
  private readonly labels = new CSS2DRenderer();
  private readonly scene = new Scene();
  private readonly camera = new OrthographicCamera(-14, 14, 7, -7, 0.1, 300);
  private readonly controls: OrbitControls;
  private readonly M: Materials;
  private readonly cards: CardFlow;
  private readonly hemi = new HemisphereLight(0xffffff, 0x9aa1ad, 0.32);
  private readonly key = new DirectionalLight(0xfff6ea, 1.6);
  private readonly spot = new SpotLight(0xfff1dc, 3.2, 0, 0.3, 0.65, 0);
  private readonly beltTex: CanvasTexture;
  private readonly grooveFill: Mesh[] = [];
  private readonly stations = new Map<RunStage, BuiltStation>();
  private readonly booth: { rise: Group; hatch: Mesh; callout: ReturnType<typeof boothCallout>; born: number | null; parts: HqParts };
  private readonly briefLine: Line<BufferGeometry, LineDashedMaterial>;
  private readonly tags: Record<"waiting" | "dropped" | "shortlisted" | "pitched", { tag: TagCallout; obj: CSS2DObject; history: number[] }>;
  private readonly resizeObserver: ResizeObserver;
  private model: CockpitModel | null = null;
  private runClock = 0;
  private follow = true;
  private glideHome = false; // after leaving follow mode, ease back to the overview once, then leave zoom to the user
  private reducedMotion = false;
  private clock = 0;
  private last = performance.now();
  private lastSpark = -1;
  private frame = 0;
  private readonly focus = new Vector3();
  private readonly offset = new Vector3();

  constructor(private readonly host: HTMLElement, dark: boolean) {
    const r = this.renderer;
    r.setPixelRatio(Math.min(devicePixelRatio, 2));
    r.setClearColor(0x000000, 0);
    r.shadowMap.enabled = true;
    r.shadowMap.type = PCFSoftShadowMap;
    r.outputColorSpace = SRGBColorSpace;
    r.toneMapping = ACESFilmicToneMapping;
    host.appendChild(r.domElement);
    Object.assign(this.labels.domElement.style, { position: "absolute", top: "0", left: "0", pointerEvents: "none" });
    host.appendChild(this.labels.domElement);

    this.scene.environment = new PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture;
    this.camera.position.copy(LOOK).addScaledVector(VIEW_DIR, 80);
    this.camera.lookAt(LOOK);
    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.target.copy(LOOK);
    Object.assign(this.controls, { enableDamping: true, enablePan: false, enableZoom: false, minZoom: 0.85, maxZoom: 2.6 });
    const polar = Math.acos(VIEW_DIR.y), az = Math.atan2(VIEW_DIR.x, VIEW_DIR.z);
    Object.assign(this.controls, { minPolarAngle: polar - 0.35, maxPolarAngle: Math.min(polar + 0.25, Math.PI / 2.2), minAzimuthAngle: az - 0.6, maxAzimuthAngle: az + 0.6 });

    this.M = new Materials(dark);
    this.lights();
    this.floor();
    this.beltTex = this.conveyor();
    this.groove();
    this.booth = this.buildBooth();
    this.briefLine = this.buildBriefLine();
    this.tags = this.buildTrays();
    this.cards = new CardFlow(this.scene);
    this.setDark(dark);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(host);
    this.resize();
    this.frame = requestAnimationFrame(this.tick);
  }

  setModel(model: CockpitModel) { this.model = model; }

  /** Seconds into the run, so step timers and the "thinking" state keep moving between events. */
  setRunClock(seconds: number) { this.runClock = seconds; }

  /** A different run: clear the floor so its stations build up again. */
  resetRun() {
    this.stations.forEach((s) => this.scene.remove(s.root));
    this.stations.clear();
    this.cards.reset();
    this.booth.born = null;
    this.booth.rise.position.y = HQ_RISE_FROM;
    this.booth.callout.root.style.opacity = "0";
    Object.values(this.tags).forEach((t) => (t.history.length = 0));
    this.grooveFill.forEach((f) => (f.scale.x = 0.0001));
    this.lastSpark = -1;
  }

  setFollow(on: boolean) {
    this.follow = on;
    this.glideHome = !on;
    this.controls.enableZoom = !on;
  }

  setReducedMotion(on: boolean) { this.reducedMotion = on; }

  setDark(dark: boolean) {
    this.M.setDark(dark);
    this.host.classList.toggle("gsf-dark", dark);
    this.hemi.groundColor.set(dark ? 0x0d1016 : 0x9aa1ad);
    this.hemi.intensity = dark ? 0.28 : 0.32;
    this.key.intensity = dark ? 1.2 : 1.6;
    this.renderer.toneMappingExposure = dark ? 1.1 : 1.0;
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.cards.dispose();
    this.scene.traverse((o) => { if (o instanceof Mesh) o.geometry.dispose(); });
    this.M.dispose();
    this.beltTex.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labels.domElement.remove();
  }

  // ---------------------------------------------------------------- scene setup

  private lights() {
    this.key.position.set(-9, 18, 12);
    this.key.castShadow = true;
    this.key.shadow.mapSize.set(2048, 2048);
    Object.assign(this.key.shadow.camera, { left: -16, right: 16, top: 10, bottom: -10, near: 1, far: 60 });
    Object.assign(this.key.shadow, { radius: 4, bias: -0.0004, normalBias: 0.02 });
    const fill = new DirectionalLight(0xdfe8ff, 0.45);
    fill.position.set(12, 8, 6);
    this.spot.position.set(HQ.x, 7, HQ.z + 1); // the Head of Sales' light shines from the control room
    this.spot.castShadow = true;
    this.scene.add(this.hemi, this.key, fill, this.spot, this.spot.target);
  }

  /** No plate: an invisible floor hides stations still below ground and catches soft shadows. */
  private floor() {
    const occluder = new Mesh(new PlaneGeometry(400, 400), new MeshBasicMaterial({ colorWrite: false }));
    occluder.rotation.x = -Math.PI / 2;
    occluder.renderOrder = -1;
    const catcher = new Mesh(new PlaneGeometry(400, 400), new ShadowMaterial({ opacity: 0.16 }));
    catcher.rotation.x = -Math.PI / 2;
    catcher.position.y = 0.001;
    catcher.receiveShadow = true;
    this.scene.add(occluder, catcher);
  }

  private conveyor(): CanvasTexture {
    const c = document.createElement("canvas");
    c.width = 128; c.height = 64;
    const g = c.getContext("2d")!;
    g.fillStyle = "#3b4048"; g.fillRect(0, 0, 128, 64);
    g.strokeStyle = "rgba(255,255,255,.10)"; g.lineWidth = 6;
    g.beginPath(); g.moveTo(40, 8); g.lineTo(70, 32); g.lineTo(40, 56); g.stroke();
    const tex = new CanvasTexture(c);
    tex.wrapS = tex.wrapT = RepeatWrapping;
    tex.repeat.set((BELT.x1 - BELT.x0) / 1.1, 1);
    tex.colorSpace = SRGBColorSpace;
    const len = BELT.x1 - BELT.x0, cx = (BELT.x0 + BELT.x1) / 2;
    for (const dz of [-0.72, 0.72]) this.scene.add(mesh(box(len + 0.3, 0.26, 0.14, 0.04), this.M.rail, cx, 0.2, BELT.z + dz));
    this.scene.add(mesh(new BoxGeometry(len, 0.04, 1.28), new MeshStandardMaterial({ map: tex, roughness: 0.9 }), cx, 0.3, BELT.z));
    for (const x of [BELT.x0, BELT.x1]) {
      const roller = mesh(new CylinderGeometry(0.16, 0.16, 1.36, 24), this.M.dark, x, 0.24, BELT.z);
      roller.rotation.x = Math.PI / 2;
      this.scene.add(roller);
    }
    for (let x = BELT.x0 + 1.5; x < BELT.x1 - 0.5; x += 3) this.scene.add(mesh(box(0.14, 0.2, 1.5, 0.03), this.M.rail, x, 0.08, BELT.z));
    return tex;
  }

  /** Progress inlaid along the front: one segment per step, filling left to right. */
  private groove() {
    this.scene.add(mesh(box(X[4] - X[0] + 4.4, 0.05, 0.3, 0.02), this.M.groove, 0, 0.025, GROOVE_Z));
    STATIONS.forEach((s, i) => {
      const geo = box(1, 0.06, 0.24, 0.02);
      geo.translate(0.5, 0, 0);
      const fill = mesh(geo, this.M.accent(AGENT_COLORS[s.agent]), X[i]! - 2.2, 0.035, GROOVE_Z);
      fill.scale.x = 0.0001;
      this.scene.add(fill);
      this.grooveFill.push(fill);
    });
  }

  private hatch(w: number, d: number): Mesh {
    const h = new Mesh(new PlaneGeometry(w, d), new MeshBasicMaterial({ color: 0x5b626e, transparent: true, opacity: 0.35, depthWrite: false }));
    h.rotation.x = -Math.PI / 2;
    h.position.y = 0.004;
    h.scale.set(0.001, 0.001, 1);
    return h;
  }

  private buildBooth() {
    const root = new Group();
    root.position.set(HQ.x, 0, HQ.z);
    const { group: rise, parts } = headquarters(this.M);
    rise.position.y = HQ_RISE_FROM;
    const hatch = this.hatch(5.6, 2.6);
    const callout = boothCallout(AGENT_COLORS.head);
    callout.root.style.opacity = "0";
    const obj = new CSS2DObject(callout.root);
    obj.center.set(0.5, 1);
    obj.position.set(0, HQ_TOP, -0.98 * HQ_SCALE);
    root.add(rise, hatch, obj);
    this.scene.add(root);
    return { rise, hatch, callout, born: null as number | null, parts };
  }

  /** A dashed line from the Head of Sales' desk to the station being briefed. */
  private buildBriefLine() {
    const line = new Line(new BufferGeometry().setFromPoints([new Vector3(), new Vector3()]),
      new LineDashedMaterial({ color: AGENT_COLORS.head, dashSize: 0.22, gapSize: 0.16, transparent: true, opacity: 0.85 }));
    line.visible = false;
    this.scene.add(line);
    return line;
  }

  private buildTrays() {
    const make = (x: number, z: number, stem: number, color: string, y = 0.36) => {
      const tag = tagCallout(color, stem);
      tag.root.style.opacity = "0";
      const obj = new CSS2DObject(tag.root);
      obj.center.set(0.5, 1);
      obj.position.set(x, y, z);
      this.scene.add(obj);
      return { tag, obj, history: [] as number[] };
    };
    const bin = tray(this.M.bin);
    bin.position.set(TRAYS.bin.x, 0, TRAYS.bin.z);
    const shortlist = tray(this.M.accent(AGENT_COLORS.qualifier), 1.2, 1.0);
    shortlist.position.set(TRAYS.shortlist.x, 0, TRAYS.shortlist.z);
    const pitches = tray(this.M.accent(AGENT_COLORS.writer), 1.2, 1.0);
    pitches.position.set(TRAYS.pitches.x, 0, TRAYS.pitches.z);
    this.scene.add(bin, shortlist, pitches);
    return {
      waiting: make(X[2] - 1.05, BELT.z, 10, AGENT_COLORS.prospector, BELT.y + 0.1),
      dropped: make(TRAYS.bin.x, TRAYS.bin.z, 10, "#6b7280"),
      shortlisted: make(TRAYS.shortlist.x, TRAYS.shortlist.z, 54, AGENT_COLORS.qualifier),
      pitched: make(TRAYS.pitches.x, TRAYS.pitches.z, 10, AGENT_COLORS.writer),
    };
  }

  private buildStation(index: number): BuiltStation {
    const spec = STATIONS[index]!;
    const color = AGENT_COLORS[spec.agent];
    const root = new Group();
    root.position.set(X[index]!, 0, 0);
    const hatch = this.hatch(3.7, 2.9);
    hatch.position.z = -1.45;
    const { rise, fluid, lamp } = shell(color, this.M);
    const { group, parts } = machine(spec.kind, color, this.M);
    rise.add(group);
    rise.position.y = -2.6;
    const callout = stationCallout(color, index, spec.title, index % 2 ? 44 : 14);
    callout.root.style.opacity = "0";
    const obj = new CSS2DObject(callout.root);
    obj.center.set(0.5, 1);
    obj.position.set(0, spec.top, -1.55);
    root.add(hatch, rise, obj);
    this.scene.add(root);
    return { born: this.clock, root, rise, hatch, fluid, lamp, parts, callout, history: [], history2: [] };
  }

  private resize() {
    const r = this.host.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this.renderer.setSize(r.width, r.height);
    this.labels.setSize(r.width, r.height);
    const home = this.camera.clone();
    home.position.copy(LOOK).addScaledVector(VIEW_DIR, 80);
    home.lookAt(LOOK);
    home.updateMatrixWorld();
    const v = new Vector3();
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const x of [BOUNDS.x0, BOUNDS.x1]) for (const y of [BOUNDS.y0, BOUNDS.y1]) for (const z of [BOUNDS.z0, BOUNDS.z1]) {
      v.set(x, y, z).applyMatrix4(home.matrixWorldInverse);
      x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y);
    }
    let w = x1 - x0 + 0.4, h = y1 - y0 + 2.4;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2 + 0.55, aspect = r.width / r.height;
    if (w / h < aspect) w = h * aspect; else h = w / aspect;
    Object.assign(this.camera, { left: cx - w / 2, right: cx + w / 2, top: cy + h / 2, bottom: cy - h / 2 });
    this.camera.updateProjectionMatrix();
  }

  // ---------------------------------------------------------------- frame loop

  private readonly tick = (now: number) => {
    const dt = Math.min(Math.max((now - this.last) / 1000, 0), 0.05); // rAF time can precede `last` on the first frame
    this.last = now;
    this.clock += dt;
    const m = this.model;
    if (m) this.animate(m, dt);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
    this.frame = requestAnimationFrame(this.tick);
  };

  private raise(rise: Group, hatch: Mesh, age: number, from: number) {
    hatch.scale.set(Math.min(age / 0.3, 1), Math.min(age / 0.3, 1), 1);
    const p = this.reducedMotion ? 1 : Math.min(Math.max((age - 0.25) / 0.95, 0), 1);
    rise.position.y = from * (1 - easeBack(p));
    hatch.visible = p < 1;
  }

  private animate(m: CockpitModel, dt: number) {
    const started = m.stagesSeen.length > 0 || m.order.length > 0;
    if (started && this.booth.born === null) this.booth.born = this.clock;
    if (this.booth.born !== null) {
      const age = this.clock - this.booth.born;
      this.raise(this.booth.rise, this.booth.hatch, age, HQ_RISE_FROM);
      this.booth.callout.root.style.opacity = age > 0.9 ? "1" : "0";
      this.booth.callout.metric.textContent = m.finished ? "run complete" : m.stage ? STAGE_VERB[m.stage] : "ready";
      this.animateHeadOfSales(m, dt);
    }
    STATIONS.forEach((spec, i) => this.animateStation(m, spec.stage, i, dt));
    this.animateMotion(m, dt);
    this.animatePiles(m);
    this.animateCamera(m, dt);
  }

  private animateStation(m: CockpitModel, stage: RunStage, i: number, dt: number) {
    const state = stageState(m, stage);
    let st = this.stations.get(stage);
    if (!st && state !== "pending") { st = this.buildStation(i); this.stations.set(stage, st); }
    if (!st) return;
    const spec = STATIONS[i]!, color = AGENT_COLORS[spec.agent];
    const age = this.clock - st.born;
    this.raise(st.rise, st.hatch, age, -2.6);
    const f = stageProgress(m, stage);
    st.fluid.scale.y += (Math.max(f, 0.001) - st.fluid.scale.y) * Math.min(dt * 8, 1);
    this.grooveFill[i]!.scale.x = Math.max(f * 4.4, 0.0001);
    const lamp = st.lamp.material as MeshStandardMaterial;
    lamp.color.set(state === "done" ? LAMP_DONE : state === "active" ? new Color(color) : LAMP_PENDING);
    st.lamp.scale.y = state === "active" && !this.reducedMotion ? 1 + (Math.sin(this.clock * 6) * 0.5 + 0.5) * 1.6 : 1;
    // callout
    const thinking = state === "active" && isThinking(m, this.runClock);
    st.callout.root.className = `gsf-callout gsf-${state}${thinking ? " gsf-thinking" : ""}`;
    st.callout.root.style.opacity = age > 0.8 ? "1" : "0";
    st.callout.metric.textContent = metric(m, stage, state);
    const label = thinking ? "thinking…" : m.agents[spec.agent].what || "working…";
    st.callout.task.textContent = `${label} · ${clock(stageElapsed(m, stage, this.runClock))}`;
    st.callout.bar.style.width = `${Math.round(f * 100)}%`;
    // motion only while working
    const on = state === "active" && !this.reducedMotion, p = st.parts;
    if (p.spin && on) p.spin.rotation.y += dt * 1.6;
    if (p.roller && on) p.roller.rotation.y += dt * 5;
    if (p.sheet) p.sheet.scale.x = 0.25 + 0.75 * f;
    if (p.bars) p.bars.forEach((b, k) => (b.scale.y = Math.max((b.userData.h as number) * Math.min(Math.max(f * 3 - k, 0), 1), 0.02)));
    if (p.needle) {
      const lastScore = m.scores.at(-1);
      const target = on && lastScore !== undefined ? (0.5 - lastScore) * 2.4 : 0;
      p.needle.rotation.z += (target - p.needle.rotation.z) * Math.min(dt * 10, 1);
    }
  }

  /** The manager faces the station it directs, leans in over its own work, and watches the pipeline board. */
  private animateHeadOfSales(m: CockpitModel, dt: number) {
    const { head, torso, bars } = this.booth.parts;
    const i = m.stage && !m.finished ? STATIONS.findIndex((s) => s.stage === m.stage) : -1;
    const k = Math.min(dt * 4, 1);
    const facing = i >= 0 ? MathUtils.clamp(Math.atan2(X[i]! - HQ.x, -1.5 - HQ.z), -1.1, 1.1) : 0;
    head.rotation.y += (facing - head.rotation.y) * k;
    const ownWork = m.stage !== null && HEAD_STAGES.has(m.stage) && !m.finished && !this.reducedMotion;
    torso.rotation.x += ((ownWork ? 0.22 + Math.sin(this.clock * 3) * 0.04 : 0) - torso.rotation.x) * k;
    // pipeline board: found → reviewed → qualified → pitched, on a log scale so small numbers still show
    const counts = pileCounts(m);
    const found = m.order.filter((id) => m.leads[id]!.found).length;
    const values = [found, m.scores.length, m.order.filter((id) => m.leads[id]!.qualified).length, counts.pitched];
    const top = Math.log1p(Math.max(...values, 1));
    bars.forEach((bar, b) => {
      const target = Math.max((Math.log1p(values[b]!) / top) * 1.3, 0.02);
      bar.scale.y += (target - bar.scale.y) * k;
    });
    // briefing line to the station being directed (not while it works on its own step)
    const line = this.briefLine;
    line.visible = i >= 0 && !HEAD_STAGES.has(m.stage!) && this.booth.rise.position.y > -0.05;
    if (line.visible) {
      const spec = STATIONS[i]!;
      line.geometry.setFromPoints([new Vector3(HQ.x, (HQ_DECK + 1.25) * HQ_SCALE, HQ.z + 0.45 * HQ_SCALE), new Vector3(X[i]!, spec.top - 0.3, -1.55)]);
      line.computeLineDistances();
    }
  }

  private animateMotion(m: CockpitModel, dt: number) {
    this.cards.update(m, dt);
    if (this.cards.beltMoving) this.beltTex.offset.x -= (dt * 3.2) / 1.1;
    const qualifier = this.stations.get("qualify")?.parts;
    if (qualifier?.scan) {
      const passing = this.cards.gateBusy;
      const target = passing ? 0.55 + (Math.sin(this.clock * 18) * 0.5 + 0.5) * 0.3 : 1.3;
      qualifier.scan.position.y += (target - qualifier.scan.position.y) * Math.min(dt * 14, 1);
    }
    if (qualifier?.paddle) qualifier.paddle.rotation.y += ((this.cards.kicking ? 0.95 : 0) - qualifier.paddle.rotation.y) * Math.min(dt * 16, 1);
    const active = m.stage ? STATIONS.findIndex((s) => s.stage === m.stage) : 4;
    this.spot.target.position.lerp(new Vector3(X[active]!, 0, -0.6), Math.min(dt * 3, 1));
  }

  private animatePiles(m: CockpitModel) {
    const counts = pileCounts(m);
    const words = { waiting: "waiting", dropped: "dropped", shortlisted: "shortlisted", pitched: "pitches" } as const;
    for (const key of Object.keys(this.tags) as (keyof typeof words)[]) {
      const { tag } = this.tags[key];
      tag.text.textContent = `${counts[key]} ${key === "pitched" && counts[key] === 1 ? "pitch" : words[key]}`;
      tag.root.style.opacity = counts[key] ? "1" : "0";
    }
    this.tags.waiting.obj.position.set(X[2] - 1.05 - Math.min(Math.max(counts.waiting - 1, 0), 4) * 0.35, BELT.y + 0.1 + Math.floor(Math.max(counts.waiting - 1, 0) / 5) * 0.042, BELT.z);
    if (this.clock - this.lastSpark < SPARK_EVERY && this.lastSpark >= 0) return;
    if (m.finished && this.lastSpark >= 0 && this.clock - this.lastSpark > 2) return; // finished: keep the last picture
    this.lastSpark = this.clock;
    for (const key of Object.keys(this.tags) as (keyof typeof words)[]) {
      const t = this.tags[key];
      if (m.order.length) t.history.push(counts[key]);
      drawSpark(t.tag.spark, t.history.slice(-120));
    }
    const qualified = m.order.filter((id) => m.leads[id]!.qualified).length;
    const series: Record<RunStage, number> = {
      plan: stageProgress(m, "plan"), search: m.order.filter((id) => m.leads[id]!.found).length, qualify: m.scores.length,
      write: counts.pitched, report: stageProgress(m, "report"),
    };
    this.stations.forEach((st, stage) => {
      st.history.push(series[stage]);
      if (stage === "qualify") st.history2.push(qualified);
      drawSpark(st.callout.spark, st.history.slice(-120), stage === "qualify" ? st.history2.slice(-120) : null);
    });
  }

  private animateCamera(m: CockpitModel, dt: number) {
    const i = m.stage ? STATIONS.findIndex((s) => s.stage === m.stage) : -1;
    const following = this.follow && i >= 0 && !m.finished;
    this.focus.set(following ? MathUtils.clamp(X[i]! - 0.2, -6.2, 6.2) : LOOK.x, LOOK.y, following ? 1.5 : LOOK.z);
    const k = this.reducedMotion ? 1 : Math.min(dt * 2.4, 1);
    this.offset.subVectors(this.camera.position, this.controls.target);
    this.controls.target.lerp(this.focus, k);
    this.camera.position.copy(this.controls.target).add(this.offset);
    if (this.follow || this.glideHome) {
      this.camera.zoom += ((following ? FOLLOW_ZOOM : 1) - this.camera.zoom) * k;
      this.camera.updateProjectionMatrix();
      if (!this.follow && Math.abs(this.camera.zoom - 1) < 0.01) this.glideHome = false;
    }
  }
}

const clock = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

function metric(m: CockpitModel, stage: RunStage, state: string): string {
  if (state === "pending") return "waiting";
  const counts = pileCounts(m);
  const found = m.order.filter((id) => m.leads[id]!.found).length;
  const reported = state === "active" ? m.progress[stage] : undefined;
  if (stage === "search") return reported && reported.total > 1 ? `${found} · ${reported.done}/${reported.total}` : String(found);
  if (stage === "qualify" && reported && reported.total > 1 && !m.scores.length) return `${reported.done}/${reported.total} checked`;
  if (stage === "qualify") return `${m.scores.length} · ${m.order.filter((id) => m.leads[id]!.qualified).length} ✓`;
  if (stage === "write") return `${counts.pitched}/3`;
  return state === "done" ? "✓" : `${Math.round(stageProgress(m, stage) * 100)}%`;
}
