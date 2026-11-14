// Animation d'accueil : deux cellules vertes en division, en SVG animé, sans bibliothèque ni ressource distante.
// Écart assumé à la charte : dégradés radiaux et transparences pour l'effet « verre » (voir docs/GUIDE_FRONT.md).
// Couleurs : uniquement l'accent vert listé dans tests/test_charte.py. Image fixe si les animations sont réduites.

const NS = "http://www.w3.org/2000/svg";
const TAU = Math.PI * 2;
const LOOP = 9000; // ms ; toutes les fréquences sont des multiples entiers de la boucle, qui se referme sans saut
const START = 0.9; // phase de la pose initiale (et de l'image fixe)
const WHITE = "#FFFFFF", PALE = "#e3f5ec", MINT = "#b8ecd2", SOFT = "#bfe6d3", LIGHT = "#86d1ae",
  MENTHE = "#6fcf9f", MID = "#3fae7f", VERT = "#1b7f58", DEEP = "#115a3d";

// Deux cellules : centre, rayon, sens de l'écartement, reflets et ombre de bord (angles, en dehors de la zone
// commune aux deux cellules) et amas intérieur (x, y, rayon, relatifs au centre).
const CELLS = [
  { x: 198, y: 176, r: 118, dir: -1, glint: [[196, 246], [254, 266]], shade: [60, 140], blobs: [
    [-14, -24, 30], [26, -34, 26], [-34, 12, 28], [16, 8, 36], [50, -6, 24],
    [-4, 46, 26], [40, 36, 24], [62, 20, 16], [-28, -46, 13], [18, -58, 11]] },
  { x: 370, y: 262, r: 124, dir: 1, glint: [[250, 292], [300, 310]], shade: [20, 110], blobs: [
    [-38, -24, 28], [2, -38, 32], [34, -12, 26], [-16, 4, 38], [18, 26, 30],
    [-46, 22, 24], [46, 26, 15], [-12, 46, 20], [-60, -10, 14], [26, -54, 12]] },
];
// Petites bulles dans chaque cellule, près de la membrane (x, y, rayon).
const INNER = [[[-70, -58, 6], [-86, 30, 4], [-40, 78, 5], [72, -66, 3.5]], [[78, -60, 5], [88, 40, 6], [30, 86, 4], [-70, 70, 3.5]]];
// Bulles libres : x, y, rayon, amplitude, fréquence, phase, type.
const BUBBLES = [
  [338, 86, 30, 9, 1, 0.2, "ring"], [214, 336, 30, 8, 1, 2.1, "glass"], [247, 305, 17, 7, 2, 1.3, "glass"],
  [302, 160, 8, 5, 2, 0.7, "drop"], [118, 302, 6, 6, 1, 3.0, "drop"], [94, 158, 5, 7, 2, 4.2, "drop"],
  [476, 148, 7, 8, 1, 5.1, "drop"], [508, 304, 9, 6, 2, 0.4, "drop"], [430, 366, 6, 7, 1, 2.6, "drop"],
  [282, 394, 9, 6, 1, 1.7, "drop"], [158, 84, 5, 6, 2, 3.6, "drop"], [258, 54, 4, 5, 1, 4.8, "drop"],
  [526, 226, 4, 5, 2, 2.2, "drop"], [272, 196, 5, 4, 2, 1.1, "glass"], [296, 240, 4, 4, 1, 3.3, "glass"], [262, 230, 3.5, 3, 2, 5.4, "glass"],
];
const DOTS = [[78, 214, 3], [190, 382, 3.5], [458, 398, 3], [544, 262, 2.5], [212, 56, 2.5], [404, 64, 2], [138, 244, 2], [472, 236, 2.2]];
const BRIDGE = [13, 11, 9.5, 8.5, 8, 8.5, 9.5, 11, 13]; // rayons de base du pont entre les deux amas
const PULL = 14; // les deux amas penchent l'un vers l'autre

let uid = 0;

function el(tag, attrs = {}, ...kids) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...kids);
  return node;
}
const radial = (id, stops, attrs = {}) => el("radialGradient", { id, ...attrs },
  ...stops.map(([offset, color, opacity = 1]) => el("stop", { offset, "stop-color": color, "stop-opacity": opacity })));
const arc = (r, from, to) => {
  const p = (a) => `${(r * Math.cos((a * Math.PI) / 180)).toFixed(1)} ${(r * Math.sin((a * Math.PI) / 180)).toFixed(1)}`;
  return `M${p(from)}A${r} ${r} 0 0 1 ${p(to)}`;
};
const f2 = (v) => v.toFixed(2);

function membrane(r, shade, ids) {
  return el("g", {},
    el("circle", { r, fill: `url(#${ids.memb})` }),
    el("circle", { r: r * 0.88, fill: "none", stroke: WHITE, "stroke-opacity": 0.5, "stroke-width": 1.6 }),
    el("circle", { r: r - 0.8, fill: "none", stroke: WHITE, "stroke-opacity": 0.6, "stroke-width": 1.4 }),
    el("path", { d: arc(r * 0.965, ...shade), fill: "none", stroke: LIGHT, "stroke-opacity": 0.45, "stroke-width": 3, "stroke-linecap": "round" }));
}
function glints(r, [main, small]) {
  return el("g", { fill: "none", stroke: WHITE, "stroke-linecap": "round" },
    el("path", { d: arc(r * 0.9, ...main), "stroke-width": 4.5, "stroke-opacity": 0.8 }),
    el("path", { d: arc(r * 0.9, ...small), "stroke-width": 3, "stroke-opacity": 0.6 }));
}
function blob(r, fill) {
  const hx = -r * 0.34, hy = -r * 0.38;
  return el("g", {},
    el("circle", { r, fill, "fill-opacity": 0.9, stroke: MENTHE, "stroke-opacity": 0.5, "stroke-width": 1 }),
    el("ellipse", { cx: hx, cy: hy, rx: r * 0.26, ry: r * 0.16, transform: `rotate(-32 ${hx} ${hy})`, fill: WHITE, "fill-opacity": 0.42 }));
}
function bubble(type, r, ids) {
  if (type === "drop") return el("g", {},
    el("circle", { r, fill: `url(#${ids.drop})` }),
    el("circle", { cx: -r * 0.32, cy: -r * 0.36, r: r * 0.3, fill: WHITE, "fill-opacity": 0.85 }));
  const g = el("g", {},
    el("circle", { r, fill: `url(#${ids.memb})` }),
    el("circle", { r: r - 0.6, fill: "none", stroke: WHITE, "stroke-opacity": 0.7, "stroke-width": 1.2 }),
    el("path", { d: arc(r * 0.78, 200, 250), fill: "none", stroke: WHITE, "stroke-width": 2.5, "stroke-opacity": 0.85, "stroke-linecap": "round" }));
  if (type === "ring") g.append(
    el("circle", { r: r * 0.64, fill: `url(#${ids.memb})`, stroke: MINT, "stroke-opacity": 0.7, "stroke-width": 1.2 }),
    el("circle", { r: r * 0.34, fill: `url(#${ids.memb})`, stroke: LIGHT, "stroke-opacity": 0.6, "stroke-width": 1 }));
  return g;
}

/** Renvoie l'élément SVG ; l'animation s'arrête d'elle-même quand la vue d'accueil est quittée. */
export function cellsAnimation() {
  const n = ++uid;
  const ids = { memb: `tr-cells-memb-${n}`, nucA: `tr-cells-nuca-${n}`, nucB: `tr-cells-nucb-${n}`,
    drop: `tr-cells-drop-${n}`, bridge: `tr-cells-pont-${n}` };
  const svg = el("svg", { viewBox: "0 0 560 420", class: "cells", role: "img", "aria-label": "Animation : deux cellules vertes en division" },
    el("defs", {},
      radial(ids.memb, [[0, PALE, 0.12], [0.55, MINT, 0.2], [0.82, LIGHT, 0.34], [0.94, MINT, 0.6], [0.985, WHITE, 0.95], [1, LIGHT, 0.6]]),
      radial(ids.nucA, [[0, PALE], [0.25, LIGHT], [0.62, MID], [0.88, VERT], [1, LIGHT]], { fx: "0.35", fy: "0.3" }),
      radial(ids.nucB, [[0, LIGHT], [0.3, MID], [0.7, VERT], [0.9, DEEP], [1, MID]], { fx: "0.35", fy: "0.3" }),
      radial(ids.drop, [[0, WHITE, 0.95], [0.4, MINT, 0.85], [1, MENTHE, 0.75]], { fx: "0.36", fy: "0.32" }),
      radial(ids.bridge, [[0, PALE], [0.4, LIGHT], [0.85, MID], [1, LIGHT]], { fx: "0.36", fy: "0.32" })));
  const scene = el("g", {});
  const layer = { memb: el("g", {}), bridge: el("g", {}), core: el("g", {}), glint: el("g", {}), free: el("g", {}) };
  scene.append(layer.memb, layer.bridge, layer.core, layer.glint, layer.free);
  svg.append(scene);

  const ax = CELLS[1].x - CELLS[0].x, ay = CELLS[1].y - CELLS[0].y, len = Math.hypot(ax, ay);
  const ux = ax / len, uy = ay / len; // axe de la division
  const cells = CELLS.map((c, i) => {
    const memb = membrane(c.r, c.shade, ids);
    for (const [x, y, r] of INNER[i]) memb.append(el("g", { transform: `translate(${x} ${y})` }, bubble("glass", r, ids)));
    const core = el("g", {}), coreWrap = el("g", {}, core), glint = glints(c.r, c.glint);
    const blobs = c.blobs.map(([x, y, r], j) => {
      const g = blob(r, `url(#${j % 3 === 1 ? ids.nucA : ids.nucB})`);
      core.append(g);
      return { g, x: x - c.dir * PULL * ux, y: y - c.dir * PULL * uy, k: 1 + (j % 3), ph: (j * 2.39 + i * 1.1) % TAU };
    });
    layer.memb.append(memb); layer.core.append(coreWrap); layer.glint.append(glint);
    return { ...c, memb, core, coreWrap, glint, blobs };
  });
  const bridge = BRIDGE.map((r, k) => {
    const c = el("circle", { r, fill: `url(#${ids.bridge})`, "fill-opacity": 0.92, stroke: MENTHE, "stroke-opacity": 0.45, "stroke-width": 1 });
    layer.bridge.append(c);
    return { c, r, k };
  });
  const free = BUBBLES.map(([x, y, r, amp, k, ph, type]) => {
    const g = bubble(type, r, ids);
    layer.free.append(g);
    return { g, x, y, amp, k, ph };
  });
  const dots = DOTS.map(([x, y, r], i) => {
    const c = el("circle", { cx: x, cy: y, r, fill: MID });
    layer.free.append(c);
    return { c, ph: i * 1.7 };
  });

  // t : phase en radians (une boucle = 2π).
  function draw(t) {
    const sep = Math.sin(t); // -1 : cellules rapprochées, 1 : écartées
    scene.setAttribute("transform", `translate(0 ${f2(4 * Math.sin(t + 1))})`);
    const centers = cells.map((c, i) => {
      const d = c.dir * 10 * sep, x = c.x + ux * d, y = c.y + uy * d;
      const base = `translate(${f2(x)} ${f2(y)}) scale(${(1 + 0.022 * Math.sin(t + i * Math.PI)).toFixed(4)})`;
      c.memb.setAttribute("transform", base);
      c.coreWrap.setAttribute("transform", base);
      c.core.setAttribute("transform", `rotate(${f2(c.dir * 6 * Math.sin(t + 0.6))})`);
      c.glint.setAttribute("transform", `${base} rotate(${f2(7 * Math.sin(t + i))})`);
      for (const b of c.blobs) {
        b.g.setAttribute("transform", `translate(${f2(b.x + 3.6 * Math.sin(b.k * t + b.ph))} ${f2(b.y + 3 * Math.cos(b.k * t + b.ph * 1.3))})`);
      }
      return [x, y];
    });
    // Pont entre les deux amas : il s'amincit quand les cellules s'écartent.
    const [[x0, y0], [x1, y1]] = centers;
    const px = x0 + ux * (44 + PULL), py = y0 + uy * (44 + PULL), qx = x1 - ux * (48 + PULL), qy = y1 - uy * (48 + PULL);
    const pinch = 0.32 + 0.22 * sep;
    for (const { c, r, k } of bridge) {
      const f = (k + 0.5) / bridge.length, bell = Math.exp(-(((f - 0.5) / 0.24) ** 2));
      const wob = (k % 2 ? 1 : -1) * (4 + 2 * Math.sin(2 * t + k));
      c.setAttribute("cx", f2(px + (qx - px) * f - uy * wob));
      c.setAttribute("cy", f2(py + (qy - py) * f + ux * wob));
      c.setAttribute("r", f2(r * (1 - pinch * bell)));
    }
    for (const b of free) {
      b.g.setAttribute("transform", `translate(${f2(b.x + b.amp * Math.sin(b.k * t + b.ph))} ${f2(b.y + b.amp * 0.8 * Math.cos(b.k * t + b.ph * 1.7))})`);
    }
    for (const d of dots) d.c.setAttribute("opacity", (0.35 + 0.4 * (0.5 + 0.5 * Math.sin(3 * t + d.ph))).toFixed(3));
  }

  draw(START);
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    let start = null, waited = 0;
    const tick = (now) => {
      if (!svg.isConnected) {
        if (start !== null || ++waited > 120) return; // vue quittée, ou jamais affichée : on arrête
        requestAnimationFrame(tick);
        return;
      }
      if (start === null) start = now;
      draw(START + (((now - start) % LOOP) / LOOP) * TAU);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  return svg;
}
