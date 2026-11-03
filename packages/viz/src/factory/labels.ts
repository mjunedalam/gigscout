import { area, line, max, curveMonotoneX, scaleLinear } from "d3";

/**
 * Callouts: a frosted-glass card, a stem and a dot that sits exactly on the thing it describes. Station cards
 * carry a mini line chart of that agent's output; pile tags carry a smaller one.
 */
export const LABEL_CSS = `
.gsf-callout { display: flex; flex-direction: column; align-items: center; transition: opacity .35s; pointer-events: none; }
.gsf-card { font: 600 11.5px Inter, system-ui, sans-serif; color: #15171d; border-radius: 11px; padding: 6px 9px;
  background: linear-gradient(160deg, rgba(255,255,255,.74), rgba(255,255,255,.44));
  -webkit-backdrop-filter: blur(12px) saturate(1.5); backdrop-filter: blur(12px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.75);
  box-shadow: 0 10px 28px -14px rgba(16,24,40,.45), inset 0 1px 0 rgba(255,255,255,.9);
  transition: border-color .3s, box-shadow .3s, opacity .3s; }
.gsf-dark .gsf-card { color: #eceef4; background: linear-gradient(160deg, rgba(40,48,64,.66), rgba(22,27,36,.46));
  border-color: rgba(255,255,255,.12); box-shadow: 0 10px 28px -14px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.08); }
.gsf-r1 { display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.gsf-r2 { display: flex; align-items: center; gap: 7px; margin-top: 3px; }
.gsf-card b { opacity: .45; font-variant-numeric: tabular-nums; }
.gsf-m { margin-left: auto; font-weight: 700; font-variant-numeric: tabular-nums; opacity: .7; }
.gsf-task { display: none; max-width: 130px; opacity: .65; font-weight: 500; font-size: 10.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gsf-stem { width: 1.5px; height: var(--stem, 14px); background: var(--c); opacity: .55; }
.gsf-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c); box-shadow: 0 0 0 2.5px rgba(255,255,255,.9), 0 1px 4px rgba(0,0,0,.3); }
.gsf-dark .gsf-dot { box-shadow: 0 0 0 2.5px rgba(20,24,36,.9), 0 1px 4px rgba(0,0,0,.5); }
.gsf-active .gsf-card { border-color: color-mix(in srgb, var(--c) 70%, white); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 16%, transparent), 0 12px 30px -14px rgba(16,24,40,.5); }
.gsf-active .gsf-m { color: var(--c); opacity: 1; } .gsf-active .gsf-task { display: block; }
.gsf-done .gsf-card { opacity: .82; } .gsf-done .gsf-m { color: #1f9d55; opacity: 1; }
.gsf-bar { height: 3px; margin-top: 5px; border-radius: 2px; background: color-mix(in srgb, var(--c) 16%, transparent); overflow: hidden; }
.gsf-bar i { display: block; height: 100%; width: 0; background: var(--c); border-radius: 2px; transition: width .4s; }
.gsf-thinking .gsf-bar i { background-image: repeating-linear-gradient(45deg, rgba(255,255,255,.45) 0 4px, transparent 4px 8px); background-size: 11.3px 11.3px; animation: gsf-stripes .7s linear infinite; }
@keyframes gsf-stripes { to { background-position: 11.3px 0; } }
@media (prefers-reduced-motion: reduce) { .gsf-thinking .gsf-bar i { animation: none; } }
.gsf-pending .gsf-bar, .gsf-done .gsf-bar { display: none; }
.gsf-tag .gsf-card { padding: 2px 8px; border-radius: 999px; font-weight: 700; font-size: 11px; }
.gsf-tag .gsf-stem { opacity: .4; }
.gsf-spark { width: 74px; height: 20px; display: block; overflow: visible; }
.gsf-tag .gsf-spark { width: 42px; height: 14px; }
.gsf-spark .a { fill: var(--c); opacity: .14; } .gsf-spark .l { fill: none; stroke: var(--c); stroke-width: 1.6; stroke-linejoin: round; }
.gsf-spark .l2 { fill: none; stroke: var(--c); stroke-width: 1.2; stroke-dasharray: 2 2; opacity: .7; } .gsf-spark .e { fill: var(--c); }
`;

const SVG_NS = "http://www.w3.org/2000/svg";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = cls;
  node.textContent = text;
  return node;
}

function spark(w: number, h: number): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "gsf-spark");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "none");
  for (const cls of ["a", "l2", "l"]) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("class", cls);
    svg.appendChild(p);
  }
  const dot = document.createElementNS(SVG_NS, "circle");
  dot.setAttribute("class", "e");
  dot.setAttribute("r", "2");
  svg.appendChild(dot);
  return svg;
}

export interface StationCallout {
  root: HTMLDivElement;
  metric: HTMLSpanElement;
  task: HTMLDivElement;
  spark: SVGSVGElement;
  bar: HTMLElement;
}

function frame(color: string, stem: number, cls: string, card: HTMLDivElement): HTMLDivElement {
  const root = el("div", `gsf-callout ${cls}`);
  root.style.setProperty("--c", color);
  root.style.setProperty("--stem", `${stem}px`);
  root.append(card, el("div", "gsf-stem"), el("div", "gsf-dot"));
  return root;
}

export function stationCallout(color: string, index: number, title: string, stem: number): StationCallout {
  const card = el("div", "gsf-card");
  const r1 = el("div", "gsf-r1");
  const metric = el("span", "gsf-m");
  r1.append(el("b", "", `0${index + 1}`), el("span", "", title), metric);
  const r2 = el("div", "gsf-r2");
  const s = spark(74, 20);
  const task = el("div", "gsf-task");
  r2.append(s, task);
  const bar = el("div", "gsf-bar");
  const fill = el("i", "");
  bar.append(fill);
  card.append(r1, r2, bar);
  return { root: frame(color, stem, "", card), metric, task, spark: s, bar: fill };
}

export interface TagCallout {
  root: HTMLDivElement;
  text: HTMLSpanElement;
  spark: SVGSVGElement;
}

export function tagCallout(color: string, stem = 10): TagCallout {
  const card = el("div", "gsf-card");
  const r1 = el("div", "gsf-r1");
  const text = el("span", "");
  const s = spark(42, 14);
  r1.append(text, s);
  card.append(r1);
  return { root: frame(color, stem, "gsf-tag", card), text, spark: s };
}

export function boothCallout(color: string): { root: HTMLDivElement; metric: HTMLSpanElement } {
  const card = el("div", "gsf-card");
  const r1 = el("div", "gsf-r1");
  const metric = el("span", "gsf-m");
  r1.append(el("span", "", "Head of Sales"), metric);
  card.append(r1);
  return { root: frame(color, 12, "gsf-active", card), metric };
}

/** Draw a mini line chart (with an optional dashed second series) into a spark SVG. */
export function drawSpark(svg: SVGSVGElement, data: number[], second: number[] | null = null) {
  if (data.length < 2) return;
  const [w, h] = svg.getAttribute("viewBox")!.split(" ").slice(2).map(Number) as [number, number];
  const top = Math.max(1, max(data) ?? 0, second ? (max(second) ?? 0) : 0);
  const x = scaleLinear([0, Math.max(data.length - 1, 12)], [1, w - 3]);
  const y = scaleLinear([0, top], [h - 2, 2]);
  const ln = line<number>().x((_, i) => x(i)).y((d) => y(d)).curve(curveMonotoneX);
  const paths = svg.querySelectorAll("path");
  paths[0]!.setAttribute("d", area<number>().x((_, i) => x(i)).y0(h).y1((d) => y(d)).curve(curveMonotoneX)(data) ?? "");
  paths[1]!.setAttribute("d", second ? (ln(second) ?? "") : "");
  paths[2]!.setAttribute("d", ln(data) ?? "");
  const dot = svg.querySelector("circle")!;
  dot.setAttribute("cx", String(x(data.length - 1)));
  dot.setAttribute("cy", String(y(data.at(-1)!)));
}
