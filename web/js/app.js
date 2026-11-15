import { ILLUSTRATION, ART } from "./illustration.js";

/* ================= utilitaires ================= */
const $ = (sel, el = document) => el.querySelector(sel);
const nf = new Intl.NumberFormat("fr-FR");
const fmt = (n) => (n == null ? "—" : nf.format(n));
const pct = (x) => (Array.isArray(x) ? x.map(pct).join(" à ") : x == null ? "non calculé" : `${Math.round(x * 100)} %`);
const labelOf = (t) => t.nct_id || t.trial_id || "Identifiant non renseigné";
const shown = (v) => v == null ? "non calculé" : v;
const powerOf = (t) => t.puissance_a_priori ? pct(t.puissance_a_priori.fourchette ?? t.puissance_a_priori.valeur) : "non calculé";
function referenceList(refs) {
  return h("ul", { class: "plain" }, Object.entries(refs || {}).map(([field, r]) =>
    h("li", {}, `${field} : ${r?.doc || (typeof r === "string" ? r : "source non renseignée")} — ${r?.passage || "passage non renseigné"}`)));
}

// Construit le DOM sans innerHTML : les textes venant des données restent du texte (pas de HTML injecté).
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v; // réservé aux constantes écrites ici (icônes)
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const ICONS = {
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2z"/><path d="M4 20a2 2 0 0 0 2 2h13v-4M8 7h7M8 11h5"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  flask: '<path d="M9 3h6M10 3v6L4.5 19a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 9V3"/><path d="M7 15h10"/>',
  ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M21 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h8"/>',
  scale: '<path d="M12 3v18M5 21h14M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  link: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  upload: '<path d="M12 15V3M7 8l5-5 5 5M5 21h14"/>',
  alert: '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
};
const icon = (name, size = 18) =>
  h("span", { class: "ic", "aria-hidden": "true", html: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>` });

async function api(path, body) {
  let res;
  try {
    res = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch (e) {
    throw new Error("Le serveur TrialRevive ne répond pas. Relancez « python server.py ».");
  }
  let data = {};
  try { data = await res.json(); } catch (e) { /* réponse non JSON */ }
  if (!res.ok) throw new Error(data.error || `Erreur ${res.status}`);
  return data;
}

/* ================= état ================= */
const state = { dossier: null, markdown: "", question: "", example: "", questions: [], source: "", fictitious: false, loading: false };
// La preuve se lit à l'intensité : plus elle est forte, plus le vert est foncé.
const E_COLOR = { E0: "#dbe4df", E1: "#bfe6d3", E2: "#86d1ae", E3: "#3fae7f", E4: "#1b7f58" };
const REJECT = {
  1: ["Exigences obligatoires", "#F5F5F5"],
  2: ["Compatibilité et puissance", "#E4E4E4"],
};
const ROUTES = {
  apercu: ["Aperçu", "grid"],
  essais: ["Essais retenus", "flask"],
  ecartes: ["Essais écartés", "ban"],
  completer: ["À compléter", "alert"],
  encours: ["En cours", "book"],
  patients: ["Patients", "users"],
  dossier: ["Dossier", "file"],
  comparaison: ["Comparaison IA", "scale"],
  guide: ["Comment ça marche", "book"],
};
const route = () => (location.hash.match(/^#\/([a-z]+)/) || [])[1] || "accueil";

/* ================= composants ================= */
function meter(level, small) {
  if (!E_COLOR[level]) return h("span", {}, "non calculé");
  const idx = Number(level.slice(1));
  const segs = [1, 2, 3, 4].map((i) => h("i", { style: i <= idx ? `background:${E_COLOR[level]}` : "" }));
  return h("div", { class: "meter" + (small ? " meter-sm" : ""), role: "img", "aria-label": `Preuve ${level}` }, segs);
}
const evidenceTag = (level) => h("span", { class: "num", style: "display:inline-flex;gap:10px;align-items:center" }, meter(level, true), h("b", {}, level));
const kindBadge = (index) => h("span", { class: "badge " + (index === "interne" ? "badge-ink" : "badge-soft") }, index === "interne" ? "Interne" : index === "externe" ? "Externe" : "Origine non renseignée");

function artRow(names) {
  return h("div", { class: "art" }, names.map((n) => h("span", { class: `art-${n}`, html: ART[n] })));
}
function pageHead(title, text, names, extra) {
  const label = ROUTES[route()]?.[0];
  return h("header", { class: "pagehead" },
    h("div", { class: "pagehead-copy" }, label && label !== title && h("p", { class: "kicker" }, label), h("h2", {}, title), text && h("p", {}, text), extra),
    names && names.length ? artRow(names) : null);
}
const HEAD_ART = {
  "Essais retenus": ["doctor", "molecule"],
  "Essais écartés": ["magnifier", "nurse"],
  "Patients de l'essai interne": ["tubes", "man"],
  "Dossier de faisabilité": ["clipboard", "doctor"],
  "Comparaison avec une IA généraliste": ["doctor", "nurse"],
};
const viewHead = (title, text, extra) => pageHead(title, text, HEAD_ART[title], extra);
function emptyState(title, text) {
  return h("section", { class: "empty" }, artRow(["clipboard", "magnifier"]), h("h3", {}, title), h("p", {}, text),
    h("a", { class: "btn btn-primary", href: "#/", style: "display:inline-grid;place-items:center;text-decoration:none" }, "Poser une question"));
}

/* ----- tiroir de détail ----- */
let lastFocus = null;
function openDrawer(content) {
  lastFocus = document.activeElement;
  $("#drawerBody").replaceChildren(content);
  $("#drawer").hidden = false;
  $("#drawer .close").focus();
}
function closeDrawer() {
  $("#drawer").hidden = true;
  lastFocus?.focus?.();
}
function trialDrawer(t) {
  const body = h("div", {}, h("p", { class: "t-sub" }, labelOf(t)), h("h3", {}, t.titre));
  if (t.retenu) {
    body.append(h("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-top:6px" }, kindBadge(t.index), evidenceTag(t.E)),
      h("dl", { class: "facts" },
        h("div", {}, h("dt", {}, "Patients randomisés"), h("dd", { class: "num" }, fmt(t.nb_patients))),
        h("div", {}, h("dt", {}, "Couverture prévue"), h("dd", { class: "num" }, pct(t.couverture))),
        h("div", {}, h("dt", {}, "Score de compatibilité"), h("dd", {}, shown(t.score))),
        h("div", {}, h("dt", {}, "Puissance a priori"), h("dd", {}, powerOf(t)))),
      h("h4", {}, "Comment obtenir la réponse"), h("p", {}, `${shown(t.R)} : ${shown(t.R_pourquoi)}`),
      h("h4", {}, "Écarts acceptés"), h("ul", {}, t.ecarts.map((v) => h("li", {}, v))),
      h("h4", {}, "À confirmer"), h("ul", {}, t.conditions.map((v) => h("li", {}, v))),
      h("h4", {}, "Gains possibles pour cet essai"), h("ul", {}, t.gains.map((g) => h("li", {}, `${g.code} : ${g.libelle}`))));
  } else if (t.statut === "a_completer") {
    body.append(h("h4", {}, "Champs manquants"), h("ul", {}, t.champs_manquants.map((v) => h("li", {}, v))));
  } else if (t.statut === "en_cours") {
    body.append(h("h4", {}, "En cours"), h("p", {}, t.motif));
  } else {
    body.append(h("h4", {}, `Exclusion à l'étage ${t.etape_rejet}`), h("ul", {}, t.raisons.map((v) => h("li", {}, v))),
      h("ul", {}, t.ecarts_avant_exclusion.map((v) => h("li", {}, v))));
  }
  if (t.avertissements.length) body.append(h("h4", {}, "À vérifier"), h("ul", {}, t.avertissements.map((v) => h("li", {}, v))));
  body.append(h("h4", {}, "Sources de la fiche"), referenceList(t.references));
  if (t.lien) body.append(h("p", { style: "margin-top:22px" }, h("a", { href: t.lien, target: "_blank", rel: "noopener" }, "Voir la fiche sur ClinicalTrials.gov")));
  return body;
}

/* ================= vues ================= */
function landing() {
  const all = state.questions.map((v, i) => ({ q: v.question, tag: i === 0 ? "Cas de démo" : v.id }));

  const input = h("input", { id: "finder", type: "text", maxlength: "600", autocomplete: "off", role: "combobox", "aria-expanded": "true", "aria-controls": "suggest",
    "aria-autocomplete": "list", "aria-label": "Rechercher une question scientifique", placeholder: "Rechercher une question scientifique" });
  const list = h("ul", { class: "suggest", id: "suggest", role: "listbox", "aria-label": "Questions proposées" });
  let active = -1, shown = [];
  const draw = () => {
    const needle = input.value.trim().toLowerCase();
    shown = all.filter((x) => !needle || x.q.toLowerCase().includes(needle));
    active = shown.length ? Math.min(active, shown.length - 1) : -1;
    list.replaceChildren(...(shown.length
      ? shown.map((x, i) => h("li", { id: `opt${i}`, role: "option", "aria-selected": String(i === active), onclick: () => { input.value = x.q; run(x.q); } },
          icon("search", 18), h("span", { class: "txt" }, x.q), h("span", { class: "tag" }, x.tag)))
      : [h("li", { role: "option", "aria-disabled": "true" }, icon("search", 18), h("span", { class: "txt" }, "Appuyez sur Entrée pour analyser cette question."))]));
    input.setAttribute("aria-activedescendant", active >= 0 ? `opt${active}` : "");
  };
  input.addEventListener("input", () => { active = -1; draw(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!shown.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
      draw();
    }
  });
  draw();

  const go = h("button", { class: "finder-go", type: "submit", "aria-label": "Analyser la question" }, icon("arrow", 20));
  const form = h("form", { onsubmit: (e) => { e.preventDefault(); run(active >= 0 && shown[active] ? shown[active].q : input.value); } }, input, go);

  return h("section", { class: "home", "aria-labelledby": "h1" },
    h("div", { class: "home-top" },
      h("div", {}, h("h1", { id: "h1" }, "Trouvez les essais qui peuvent répondre à votre question"), h("p", { class: "lede" }, "Une question entre. Un dossier de faisabilité sort.")),
      h("div", { class: "illus", html: ILLUSTRATION })),
    h("div", { class: "finder" }, form, list),
    h("p", { class: "home-note" }, state.fictitious ? "Démonstration sur fiches entièrement fictives." : "Données de la base configurée. Aucun comptage individuel de patients.",
      state.dossier && [" ", h("a", { href: "#/apercu" }, "Revenir au dernier dossier")]),
  );
}

function resultSummary(d) {
  const pending = [
    d.a_completer.length && h("a", { href: "#/completer" }, `${fmt(d.a_completer.length)} à compléter`),
    d.en_cours.length && h("a", { href: "#/encours" }, `${fmt(d.en_cours.length)} en cours`),
  ].filter(Boolean);
  return h("section", { class: "result-summary", "aria-label": "Chiffres clés" },
    h("div", { class: "rpanel" }, h("p", { class: "k" }, "Essais examinés"),
      h("p", { class: "v num" }, fmt(d.rejection.total)),
      pending.length ? h("p", { class: "d pending-counts" }, pending) : null),
    h("div", { class: "rpanel key" }, h("p", { class: "k" }, "Essais retenus"),
      h("p", { class: "v num" }, fmt(d.retenus.length)),
      h("p", { class: "d" }, `${fmt(d.internes.length)} interne${d.internes.length > 1 ? "s" : ""} · ${fmt(d.externes.length)} externe${d.externes.length > 1 ? "s" : ""}`)),
    h("div", { class: "rpanel" }, h("p", { class: "k" }, "Essais écartés"),
      h("p", { class: "v num" }, fmt(d.ecartes.length)),
      h("a", { class: "metric-link", href: "#/ecartes" }, "Voir les motifs")));
}

function retainedPreview(d) {
  return h("section", { class: "section retained-preview", "aria-labelledby": "retained-title" },
    h("div", { class: "result-section-head" }, h("h3", { id: "retained-title" }, "Essais retenus"),
      d.retenus.length > 0 && h("a", { href: "#/essais" }, "Tout voir", icon("arrow", 16))),
    d.retenus.length > 3 && h("p", { class: "t-sub preview-count" }, `Aperçu de 3 essais sur ${fmt(d.retenus.length)} retenus.`),
    d.retenus.length ? h("ul", { class: "trial-preview" }, d.retenus.slice(0, 3).map((t) =>
      h("li", {}, h("button", { class: "trial-preview-button", type: "button", onclick: () => openDrawer(trialDrawer(t)) },
        h("span", { class: "trial-preview-info" }, h("span", { class: "t-title" }, t.titre),
          h("span", { class: "trial-preview-meta" }, kindBadge(t.index), h("span", { class: "t-sub" }, labelOf(t)),
            E_COLOR[t.E] && h("span", { class: "badge badge-soft" }, `Preuve ${t.E}`))),
        icon("arrow", 18)))))
      : h("p", { class: "sub" }, "Aucun essai retenu pour cette question."));
}

function funnelBars(d, withDrops) {
  if (!d.entonnoir.length) return h("p", { class: "note" }, d.raison_indetermination);
  const top = d.entonnoir[0].n || 1;
  return h("div", { class: "funnel" }, d.entonnoir.map((st, i) => {
    const [code, ...rest] = st.etape.split(" : ");
    const prev = i ? d.entonnoir[i - 1].n : null;
    const bar = h("i", { style: `width:${(100 * st.n) / top}%` });
    return h("div", { class: "frow" + (code.startsWith("S4") ? " final" : "") },
      h("div", { class: "lab" }, h("b", {}, code), rest.length ? ` : ${rest.join(" : ")}` : ""),
      h("div", { class: "bar" }, bar),
      h("div", { class: "val num" }, st.n_publie == null ? "<5" : fmt(st.n_publie), withDrops && prev != null && st.n < prev ? h("small", {}, `−${prev - st.n}`) : ""),
    );
  }));
}

function overview() {
  const d = state.dossier;
  return h("div", { class: "overview" },
    pageHead("Résultats de l'analyse", d.question, ["clipboard"]),
    resultSummary(d), retainedPreview(d),
    h("section", { class: "result-actions panel-box", "aria-label": "Dossier de faisabilité" },
      h("div", {}, h("h3", {}, "Dossier de faisabilité"), h("p", {}, "Résultats détaillés, conditions et sources.")),
      h("div", { class: "result-actions-buttons" },
        h("a", { class: "btn btn-primary", href: "#/dossier" }, icon("file", 16), "Ouvrir le dossier"),
        h("a", { class: "btn btn-ghost", href: `/api/dossier.md?question=${encodeURIComponent(state.question)}`, download: "dossier_trialrevive.md" },
          icon("download", 16), "Télécharger"))));
}

function trialsView() {
  const d = state.dossier;
  const table = (items, title) => h("section", { class: "section" }, h("h3", {}, `${title} (${items.length})`),
    items.length ? h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Rang", "Essai", "Origine", "Patients randomisés", "Preuve", "Score", "Couverture prévue", "Puissance a priori"].map((v) => h("th", {}, v)))),
      h("tbody", {}, items.map((t, i) => h("tr", { tabindex: "0", onclick: () => openDrawer(trialDrawer(t)),
        onkeydown: (e) => { if (e.key === "Enter") openDrawer(trialDrawer(t)); } },
        h("td", { class: "num" }, i + 1), h("td", {}, h("div", { class: "t-title" }, t.titre), h("div", { class: "t-sub" }, labelOf(t))),
        h("td", {}, kindBadge(t.index)), h("td", { class: "right num" }, fmt(t.nb_patients)), h("td", {}, evidenceTag(t.E)),
        h("td", { class: "right num" }, shown(t.score)), h("td", { class: "right num" }, pct(t.couverture)), h("td", { class: "right num" }, powerOf(t)))))))
      : h("p", { class: "note" }, "Aucun essai retenu dans ce groupe."));
  return h("div", {}, viewHead("Essais retenus", "Classements internes et externes séparés, dans l'ordre fourni par le moteur. Cliquez une ligne pour les conditions et les sources."),
    table(d.internes, "Essais internes"), table(d.externes, "Essais externes"));
}

function rejectedView() {
  const d = state.dossier;
  let q = "", only = null;
  const counts = {};
  d.ecartes.forEach((t) => (counts[t.etape_rejet] = (counts[t.etape_rejet] || 0) + 1));
  const body = h("tbody");
  const draw = () => {
    const rows = d.ecartes.filter((t) => (only == null || t.etape_rejet === only) && (`${t.titre} ${labelOf(t)} ${t.raison}`).toLowerCase().includes(q));
    body.replaceChildren(...(rows.length ? rows.map((t) => h("tr", { tabindex: "0", onclick: () => openDrawer(trialDrawer(t)), onkeydown: (e) => { if (e.key === "Enter") openDrawer(trialDrawer(t)); } },
      h("td", {}, h("div", { class: "t-title" }, t.titre), h("div", { class: "t-sub" }, labelOf(t))), h("td", {}, t.raison))) : [h("tr", {}, h("td", { colspan: 2 }, "Aucun essai ne correspond à ce filtre."))]));
    count.textContent = `${rows.length} essai${rows.length > 1 ? "s" : ""} affiché${rows.length > 1 ? "s" : ""}`;
  };
  const count = h("span", { class: "t-sub", style: "font-family:inherit" });
  const chips = h("div", { class: "chips" }, Object.keys(counts).map(Number).sort().map((n) =>
    h("button", { class: "chip", type: "button", "aria-pressed": "false", onclick: (e) => {
      only = only === n ? null : n;
      chips.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
      if (only != null) e.currentTarget.setAttribute("aria-pressed", "true");
      draw();
    } }, `${REJECT[n][0]} (${counts[n]})`)));
  draw();
  return h("div", {}, viewHead("Essais écartés", "Chaque essai écarté garde la raison qui l'a exclu. Filtrez par raison ou cherchez un titre."),
    h("div", { class: "toolbar" }, h("input", { type: "search", placeholder: "Chercher un essai", "aria-label": "Chercher un essai écarté", oninput: (e) => { q = e.target.value.toLowerCase(); draw(); } }), count),
    h("div", { class: "toolbar" }, chips),
    h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Essai"), h("th", {}, "Raison de l'écart"))), body)));
}

function pendingView(kind) {
  const items = state.dossier[kind];
  const title = kind === "a_completer" ? "À compléter" : "En cours";
  return h("div", {}, viewHead(title, kind === "a_completer" ? "Ces fiches demandent des informations supplémentaires ; elles ne sont pas exclues." : "Ces essais ne sont pas encore commencés à la date de l'hypothèse ; ils ne sont pas exclus."),
    items.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Essai"), h("th", {}, "Détail"))),
      h("tbody", {}, items.map((t) => h("tr", { tabindex: "0", onclick: () => openDrawer(trialDrawer(t)), onkeydown: (e) => { if (e.key === "Enter") openDrawer(trialDrawer(t)); } },
        h("td", {}, h("div", { class: "t-title" }, t.titre), h("div", { class: "t-sub" }, labelOf(t))),
        h("td", {}, kind === "a_completer" ? t.champs_manquants.join(", ") : t.motif))))))
      : h("p", { class: "note" }, "Aucun essai dans ce statut."));
}

function patientsView() {
  const d = state.dossier, st = d.statistique, c = d.essai_confirmation;
  return h("div", {}, viewHead("Patients de l'essai interne", "Les fiches d'essais fournissent des effectifs randomisés ; le comptage individuel n'est pas disponible."),
    h("div", { class: "hero-num" }, h("span", { class: "b" }, "Non calculé"), h("p", { class: "d" }, d.raison_indetermination)),
    h("section", { class: "section" }, h("h3", {}, "Exigence statistique de l'hypothèse"),
      h("p", { class: "sub" }, `${fmt(st.evenements_necessaires_total)} événements nécessaires au total pour l'interaction. Ce nombre n'est pas un effectif observé.`),
      h("div", { class: "panel-box" }, h("dl", { class: "doc kv", style: "max-width:none" },
        h("dt", {}, "Effets attendus (hypothèses)"), h("dd", {}, `HR+ : ${shown(st.hypotheses.hr_x_plus)} ; HR− : ${shown(st.hypotheses.hr_x_moins)}`),
        h("dt", {}, "Événements individuels observés"), h("dd", {}, "Non calculés"),
        h("dt", {}, "Essai de confirmation"), h("dd", {}, `${fmt(c.evenements_tous)} événements ouvert à tous, ${fmt(c.evenements_selectionnes)} réservé au sous-groupe ciblé`)))));
}

function dossierView() {
  const d = state.dossier, st = d.statistique, c = d.essai_confirmation;
  const link = `/api/dossier.md?question=${encodeURIComponent(state.question)}`;
  const listGroup = (key, title) => {
    const rows = d[key].map((t) => h("li", {},
      t.lien ? h("a", { href: t.lien, target: "_blank", rel: "noopener" }, labelOf(t)) : labelOf(t),
      ` : ${t.titre} (${fmt(t.nb_patients)} patients randomisés, preuve ${shown(t.E)}, voie ${shown(t.R)})`,
      h("ul", {}, t.gains.map((g) => h("li", {}, `${g.code} : ${g.libelle}`)))));
    return [h("h3", {}, `${title} (${d[key].length})`), h("ul", {}, rows)];
  };
  return h("div", {}, viewHead("Dossier de faisabilité", d.question, h("div", { style: "margin-top:16px" },
    h("a", { class: "btn btn-primary btn-small", href: link, download: "dossier_trialrevive.md", style: "display:inline-flex;gap:8px;align-items:center;text-decoration:none" }, icon("download", 16), "Télécharger en Markdown"))),
    h("div", { class: "doc panel-box" },
      h("h3", {}, "Verdicts par essai"), h("p", {}, d.verdict.E_pourquoi),
      listGroup("internes", "Essais internes retenus"), listGroup("externes", "Essais externes retenus"),
      h("h3", {}, `Essais exclus (${d.ecartes.length})`), h("ul", {}, d.ecartes.map((t) => h("li", {}, `${labelOf(t)} : ${t.raison}`))),
      h("h3", {}, `Fiches à compléter (${d.a_completer.length})`), h("ul", {}, d.a_completer.map((t) => h("li", {}, `${labelOf(t)} : ${t.champs_manquants.join(", ")}`))),
      h("h3", {}, `Essais en cours (${d.en_cours.length})`), h("ul", {}, d.en_cours.map((t) => h("li", {}, `${labelOf(t)} : ${t.motif}`))),
      h("h3", {}, "Données internes"), h("p", {}, d.raison_indetermination),
      h("h3", {}, "Exigence statistique"), h("p", {}, `${fmt(st.evenements_necessaires_total)} événements nécessaires au total pour l'interaction, selon les hypothèses de la SEH.`),
      h("p", {}, `Essai de confirmation : ${fmt(c.evenements_tous)} événements ouvert à tous ; ${fmt(c.evenements_selectionnes)} réservé au sous-groupe ciblé.`),
      h("h3", {}, "Sources"), h("ul", {}, d.sources.map((t) => h("li", {}, t.lien ? h("a", { href: t.lien, target: "_blank", rel: "noopener" }, labelOf(t)) : labelOf(t), referenceList(t.references)))),
      h("h3", {}, "Limites"), h("ul", {}, d.limites.map((t) => h("li", {}, t)))));
}

function guideView() {
  const step = (n, art, title, text) => h("li", { class: "gstep" }, h("span", { class: "gart", html: ART[art] }),
    h("div", {}, h("h3", {}, h("span", { class: "gnum num" }, n), title), h("p", {}, text)));
  return h("div", {}, pageHead("Comment ça marche", "Une hypothèse structurée, des fiches d'essais et un dossier de faisabilité.", ["man", "doctor", "nurse"]),
    h("ol", { class: "gsteps" },
      step(1, "clipboard", "Choisir une hypothèse", "Le cas proposé correspond à une fiche SEH déjà configurée. La traduction automatique des questions libres n'est pas disponible."),
      step(2, "molecule", "Comparer les essais", "Le moteur applique les exigences, les tolérances et la puissance a priori. Les essais internes et externes sont classés séparément."),
      step(3, "tubes", "Distinguer les statuts", "Retenu, exclu, à compléter ou en cours : chaque résultat conserve son statut. Le comptage individuel S0 à S4 n'est pas encore calculé."),
      step(4, "heart", "Lire le dossier", "Les voies, niveaux de preuve atteignables, gains et conditions sont fournis par essai. Aucun verdict global n'est ajouté.")),
    h("section", { class: "section" }, h("h3", {}, "Ce qui reste à valider"), h("div", { class: "panel-box" }, h("ul", { class: "plain" },
      h("li", {}, "Les paramètres scientifiques et les sources doivent être relus par l'équipe Science."),
      h("li", {}, "Une valeur de couverture ou d'événements prévue n'est pas une observation clinique."),
      h("li", {}, "Les jeux de démonstration sont fictifs. Aucun patient réel n'est utilisé."),
      h("li", {}, "La comparaison IA utilise uniquement des réponses réellement importées.")))));
}

async function comparisonView() {
  const wrap = h("div", {}, viewHead("Comparaison avec une IA généraliste", "Importez la réponse réelle d'une IA à la même question. Rien n'est inventé : sans réponse importée, aucune comparaison n'est affichée."));
  const file = h("input", { type: "file", accept: "application/json,.json", class: "sr", id: "importFile" });
  const importBtn = h("label", { class: "btn btn-ghost btn-small", for: "importFile", style: "display:inline-flex;gap:8px;align-items:center;cursor:pointer" }, icon("upload", 16), "Importer une réponse (JSON)");
  const msg = h("p", { role: "status", style: "color:var(--ink2);margin-top:8px" });
  let records = [], errors = [], current = null, imported = null;
  try { const r = await api("/api/baselines"); records = r.records; errors = r.errors; } catch (e) { errors = [e.message]; }
  const detail = h("div", {});
  const list = h("div", { class: "rec-list" });

  const select = async (rec, isImported) => {
    current = rec; imported = isImported ? rec : null;
    list.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.__rec === rec)));
    detail.replaceChildren(h("p", {}, "Chargement…"));
    try {
      const r = await api("/api/compare", { question: state.question, record: rec });
      const keys = ["Critère", "TrialRevive", "IA généraliste (évaluation déclarée)"];
      detail.replaceChildren(
        h("h3", { style: "font-size:1.1rem;margin-bottom:6px" }, rec.question),
        h("p", { class: "t-sub", style: "font-family:inherit" }, `Modèle : ${rec.modele}. Date : ${rec.date}.`),
        rec.contexte && h("p", { style: "margin-top:6px" }, `Contexte : ${rec.contexte}`),
        !r.meme_question && h("p", { class: "note" }, "La question archivée diffère de la question analysée : les résultats TrialRevive ne sont pas comparables."),
        h("div", { class: "table-wrap", style: "margin-top:14px" }, h("table", {}, h("thead", {}, h("tr", {}, keys.map((k) => h("th", {}, k)))), h("tbody", {}, r.rows.map((row) => h("tr", {}, keys.map((k) => h("td", {}, row[k]))))))),
        h("h4", { style: "margin:20px 0 8px;font:650 1rem var(--display)" }, "Réponse brute, intégrale"),
        h("textarea", { class: "raw", readonly: true, "aria-label": "Réponse brute de l'IA" }, rec.reponse_ia),
        h("h4", { style: "margin:20px 0 8px;font:650 1rem var(--display)" }, "Numéros NCT cités"),
        h("p", { class: "t-sub", style: "font-family:inherit;margin-bottom:8px" }, "Retrouver un essai dans les fiches chargées ne valide ni les chiffres, ni la conclusion. Un NCT absent peut exister."),
        r.nct.length ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["NCT cité", "Cache local", "Titre du registre", "Lien"].map((k) => h("th", {}, k)))),
          h("tbody", {}, r.nct.map((n) => h("tr", {}, h("td", { class: "num" }, n["NCT cité"]), h("td", {}, n["Cache local"]), h("td", {}, n["Titre du registre"]),
            h("td", {}, h("a", { href: n["Lien"], target: "_blank", rel: "noopener" }, "Ouvrir"))))))) : h("p", {}, "Aucun numéro NCT détecté : les autres références restent à vérifier."),
        h("div", { style: "display:flex;gap:10px;margin-top:18px;flex-wrap:wrap" },
          h("button", { class: "btn btn-ghost btn-small", type: "button", onclick: () => {
            const url = URL.createObjectURL(new Blob([JSON.stringify(rec, null, 2)], { type: "application/json" }));
            h("a", { href: url, download: "comparaison_ia.json" }).click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
          } }, "Télécharger l'archive JSON"),
          imported && h("button", { class: "btn btn-primary btn-small", type: "button", onclick: async () => {
            try { const a = await api("/api/baselines/archive", { record: imported }); msg.textContent = `Réponse archivée localement : ${a.archive}`; }
            catch (e) { msg.textContent = `Archivage impossible : ${e.message}`; }
          } }, "Archiver cette réponse localement")),
      );
    } catch (e) { detail.replaceChildren(h("p", { class: "alert", style: "margin:0" }, e.message)); }
  };
  const addToList = (rec, isImported) => {
    const b = h("button", { type: "button", "aria-pressed": "false", onclick: () => select(rec, isImported) }, h("b", {}, rec.modele), h("small", {}, `${rec.date}${isImported ? " (importée)" : ""}`));
    b.__rec = rec; list.append(b); return b;
  };
  records.forEach((r) => addToList(r, false));
  file.addEventListener("change", async () => {
    const f = file.files[0]; if (!f) return;
    try {
      if (f.size > 1_500_000) throw new Error("Fichier trop volumineux (1,5 Mo maximum).");
      const r = await api("/api/baselines/validate", { text: await f.text() });
      const b = addToList(r.record, true); msg.textContent = ""; b.click(); empty.hidden = true;
    } catch (e) { msg.textContent = `Import impossible : ${e.message}`; }
    file.value = "";
  });
  const empty = h("div", { class: "empty", hidden: records.length > 0 }, h("h3", {}, "Aucune réponse d'IA enregistrée"),
    h("p", {}, "Posez la même question à une IA généraliste, copiez sa réponse complète dans un fichier JSON (modèle et protocole dans data/baseline/LISEZ_MOI.md), puis importez-le ici. Aucune comparaison n'a encore été effectuée."));
  wrap.append(h("div", { class: "toolbar" }, file, importBtn), msg, ...errors.map((e) => h("p", { class: "note" }, e)), empty,
    h("div", { class: "cmp-layout" }, list, detail));
  if (records.length) list.firstChild.click();
  return wrap;
}

/* ================= pilotage ================= */
function setAlert(text) { const a = $("#alert"); a.textContent = text || ""; a.hidden = !text; }

function setBusy(on) {
  $("#progress").hidden = !on;
  document.querySelectorAll(".ask button[type=submit]").forEach((b) => { b.disabled = on; b.textContent = on ? "Analyse…" : "Analyser"; });
  document.querySelectorAll(".finder-go").forEach((b) => { b.disabled = on; });
}

async function run(text) {
  text = (text || "").trim();
  if (!text) { setAlert("Écrivez une question avant de lancer l'analyse, ou cliquez sur « Cas de démo »."); return; }
  if (state.loading) return;
  state.loading = true; setAlert("");
  setBusy(true);
  try {
    const res = await api("/api/analyze", { question: text });
    Object.assign(state, { dossier: res.dossier, markdown: res.markdown, question: text, example: res.exemple });
    $("#qCompact").value = text;
    if (route() === "apercu") render(); else location.hash = "#/apercu";
  } catch (e) {
    setAlert(e.message);
  } finally {
    state.loading = false;
    setBusy(false);
  }
}

function renderNav(current) {
  const d = state.dossier;
  $("#nav").replaceChildren(...Object.entries(ROUTES).map(([id, [label, ic]]) => {
    const count = d && id === "essais" ? d.retenus.length : d && id === "ecartes" ? d.ecartes.length : d && id === "completer" ? d.a_completer.length : d && id === "encours" ? d.en_cours.length : null;
    return h("li", {}, h("a", { href: `#/${id}`, "aria-current": current === id ? "page" : null }, icon(ic, 19), h("span", {}, label), count != null && h("span", { class: "count num" }, count)));
  }));
}

async function render() {
  $("#drawer").hidden = true;
  const r = route();
  document.body.dataset.state = r === "accueil" ? "landing" : "work";
  renderNav(r);
  const main = $("#main");
  let view;
  if (r === "accueil") view = landing();
  else if (!ROUTES[r]) view = emptyState("Cette page n'existe pas", "Revenez à l'accueil pour poser une question.");
  else if (!state.dossier && r !== "guide") view = emptyState("Aucune analyse pour le moment", "Posez une question, ou lancez le cas de démonstration : les essais, les patients et le dossier apparaîtront ici.");
  else view = { apercu: overview, essais: trialsView, ecartes: rejectedView, completer: () => pendingView("a_completer"), encours: () => pendingView("en_cours"), patients: patientsView, dossier: dossierView, comparaison: comparisonView, guide: guideView }[r]();
  const node = await view;
  main.replaceChildren(node);
  document.title = r === "accueil" ? "TrialRevive" : `${ROUTES[r]?.[0] ?? "Page introuvable"} | TrialRevive`;
  if (r !== "accueil") window.scrollTo({ top: 0 });
}

/* ================= démarrage ================= */
$("#askFormCompact").addEventListener("submit", (e) => { e.preventDefault(); run($("#qCompact").value); });
$("[data-demo]").addEventListener("click", () => run(state.example));
document.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDrawer(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#drawer").hidden) closeDrawer();
  if (e.key === "/" && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); ($("#finder") || $("#qCompact")).focus(); }
});
addEventListener("hashchange", render);
api("/api/info").then((i) => {
  state.example = i.exemple; state.questions = i.questions; state.source = i.source; state.fictitious = i.donnees_fictives;
  $("#qCompact").placeholder = "Choisissez une hypothèse proposée";
  $("#sourceMode").textContent = i.donnees_fictives ? "Démonstration fictive" : i.source === "postgres" ? "Source : PostgreSQL" : "Source : fichier fourni";
}).catch((e) => setAlert(e.message)).finally(render);
