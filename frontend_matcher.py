"""Adaptation de présentation du résultat Backend/matcher.py vers le contrat web.

Aucune règle de sélection, puissance, score ou niveau de preuve n'est recalculée.
Les absences du backend (patients S4, survies, verdict global) restent explicites.
"""
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from src import compare

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "Backend"
PATIENTS_NON_CALCULES = "Le comptage individuel S0 à S4 n'est pas calculé par cette analyse."


class BackendUnavailable(RuntimeError):
    """Message public produit sans URI de connexion ou erreur brute du pilote."""


def trial_label(row):
    return row.get("nct_id") or row.get("trial_id") or "Identifiant non renseigné"


def registry_link(fiche):
    nct = fiche.get("nct_id")
    if isinstance(nct, str) and re.fullmatch(r"NCT\d{8}", nct):
        return nct, f"https://clinicaltrials.gov/study/{nct}"
    return None, None


def adapt_result(bundle, *, source, fictitious=False):
    """Renomme les champs et conserve les cinq listes et leur ordre d'origine."""
    raw, seh = bundle["resultat"], bundle["seh"]
    by_id = {f["trial_id"]: f for f in bundle["fiches"]}

    def row(value, status, index=None):
        fiche = by_id.get(value["trial_id"], {})
        nct, link = registry_link(fiche)
        voie = value.get("voie") or {}
        return {"trial_id": value["trial_id"], "nct_id": nct, "lien": link,
                "titre": value.get("titre") or "Titre non renseigné", "index": index or fiche.get("index"),
                "statut": status, "retenu": True if status == "retenu" else False if status == "exclu" else None,
                "niveau": None, "nb_patients": value.get("effectif_randomise", fiche.get("effectif_randomise")),
                "score": value.get("score_compatibilite"), "bonus": value.get("bonus_ideal"),
                "E": value.get("niveau_preuve_atteignable"), "plafond": None,
                "R": voie.get("code"), "R_pourquoi": voie.get("explication"),
                "couverture": value.get("couverture_prevue"), "ecarts": value.get("ecarts", []),
                "conditions": value.get("conditions_restantes", []),
                "puissance_a_priori": value.get("puissance_a_priori"),
                "gains": value.get("gains", []), "detenteur": value.get("detenteur"),
                "etape_rejet": value.get("etage"), "raisons": value.get("raisons", []),
                "raison": " ; ".join(value.get("raisons", [])),
                "ecarts_avant_exclusion": value.get("ecarts_avant_exclusion", []),
                "motif": value.get("motif"), "avertissements": value.get("avertissements", []),
                "champs_manquants": value.get("champs_manquants", []),
                "references": value.get("sources", fiche.get("sources", {}))}

    internes = [row(r, "retenu", "interne") for r in raw["internes"]]
    externes = [row(r, "retenu", "externe") for r in raw["externes"]]
    excluded = [row(r, "exclu") for r in raw["exclus"]]
    incomplete = [row(r, "a_completer") for r in raw["a_completer"]]
    ongoing = [row(r, "en_cours") for r in raw.get("en_cours", [])]
    stage_labels = {1: "Étage 1 : exigences obligatoires", 2: "Étage 2 : compatibilité et puissance"}
    rejection = {"total": raw["n_essais_examines"], "retenus": len(internes) + len(externes),
                 "ecartes_par_etape": {label: sum(r["etape_rejet"] == stage for r in excluded)
                                       for stage, label in stage_labels.items()},
                 "etapes": stage_labels}
    sizing = raw["taille_essai_confirmation"]
    sources = [{"trial_id": r["trial_id"], "nct_id": r["nct_id"], "lien": r["lien"],
                "reanalyse": None, "publication_lien": None, "reanalyse_verifiee": None,
                "references": r["references"]} for r in internes + externes]
    return {"backend": "Backend/matcher.py", "question": raw["enonce"], "seh_id": raw["seh_id"],
            "seh_version": raw["version"], "source_donnees": source, "donnees_fictives": fictitious,
            "internes": internes, "externes": externes, "retenus": internes + externes,
            "ecartes": excluded, "a_completer": incomplete, "en_cours": ongoing,
            "rejection": rejection, "n_lignes_recues": raw["n_lignes_recues"],
            "entonnoir": [], "utilisables": None, "statut_comptage": "non calculé",
            "raison_indetermination": PATIENTS_NON_CALCULES, "groupes": [],
            "verdict": {"R": None, "E": None, "G": [], "preuve_verifiee": None,
                        "R_texte": "Voies disponibles par essai", "E_texte": "Niveaux disponibles par essai",
                        "E_pourquoi": "Le backend fournit des verdicts par essai, sans verdict global."},
            "statistique": {"evenements_necessaires_total": raw["exigence_statistique"]["evenements_min"],
                            "evenements_necessaires_par_groupe": None, "evenements_internes": {},
                            "suffisant": None, "hr_hypothese": None, "hypotheses": seh["effets_attendus"],
                            "exigence": raw["exigence_statistique"]},
            "essai_confirmation": {"hr_dilue": sizing.get("hr_dilue_tous"),
                                   "evenements_tous": sizing.get("evenements_essai_tous"),
                                   "evenements_selectionnes": sizing.get("evenements_essai_x_plus"),
                                   "hypotheses": sizing.get("hypotheses")},
            "gain": {"pct_sauvage": None, "gain_sauvage_mois": None, "gain_mute_mois": None,
                     "note": "Les gains de survie individuels ne sont pas calculés ; les gains possibles figurent par essai."},
            "sources": sources, "source_hypothese": seh.get("source"),
            "methode": "Appariement selon l'hypothèse structurée : exigences obligatoires, compatibilité, puissance a priori et verdict par essai.",
            "limites": [PATIENTS_NON_CALCULES, "Aucun verdict global R/E/G n'est calculé.",
                        "Les essais internes et externes sont classés séparément par le backend.",
                        "L'hypothèse et les paramètres scientifiques restent à valider ; les sources sont celles des fiches fournies.",
                        "La couverture et certains taux peuvent être des hypothèses signalées dans les fiches."]}


def to_markdown(d):
    lines = ["# Dossier de faisabilité", "", d["question"], "",
             f"Hypothèse {d['seh_id']} v{d['seh_version']} — source : {d['source_donnees']}.",
             f"{d['rejection']['total']} essais examinés ; {d['n_lignes_recues']} lignes reçues.",
             "\n## Verdicts par essai", d["verdict"]["E_pourquoi"]]
    for key, title in (("internes", "Essais internes retenus"), ("externes", "Essais externes retenus")):
        lines.append(f"\n## {title} ({len(d[key])})")
        for r in d[key]:
            identifier = f"[{trial_label(r)}]({r['lien']})" if r["lien"] else trial_label(r)
            lines.append(f"- {identifier} : {r['titre']} — {r['nb_patients']} patients randomisés, "
                         f"score {r['score']}, preuve atteignable {r['E']}, voie {r['R']}.")
            lines += [f"  - Écart : {v}" for v in r["ecarts"]]
            lines += [f"  - À confirmer : {v}" for v in r["conditions"]]
            lines += [f"  - {g['code']} : {g['libelle']}" for g in r["gains"]]
    for key, title in (("ecartes", "Essais exclus"), ("a_completer", "Fiches à compléter"), ("en_cours", "Essais en cours")):
        lines.append(f"\n## {title} ({len(d[key])})")
        for r in d[key]:
            detail = r["raison"] or r.get("motif") or ", ".join(r["champs_manquants"])
            lines.append(f"- {trial_label(r)} : {r['titre']} — {detail}")
    st, sizing = d["statistique"], d["essai_confirmation"]
    lines += ["\n## Données internes", d["raison_indetermination"],
              "\n## Exigence statistique", f"{st['evenements_necessaires_total']} événements nécessaires au total pour l'interaction (hypothèses de la SEH).",
              f"Essai de confirmation : {sizing['evenements_tous']} événements ouvert à tous, "
              f"{sizing['evenements_selectionnes']} réservé au sous-groupe ciblé.", "\n## Sources"]
    for s in d["sources"]:
        lines.append(f"- {trial_label(s)}" + (f" — {s['lien']}" if s["lien"] else " — lien non renseigné"))
        for field, ref in s["references"].items():
            lines.append(f"  - {field} : {ref.get('doc') or 'source non renseignée'} ; {ref.get('passage') or 'passage non renseigné'}")
    if d["source_hypothese"]:
        lines.append(f"- Hypothèse : {d['source_hypothese'].get('doc')} ; {d['source_hypothese'].get('passage')}")
    lines += ["\n## Limites", *[f"- {v}" for v in d["limites"]]]
    return "\n".join(lines) + "\n"


class BackendFrontendService:
    def __init__(self, *, fiches=None, seh=None, corpus=None, timeout=180, cache_seconds=30):
        self.fiches = Path(fiches).resolve() if fiches is not None else None
        self.seh = Path(seh).resolve() if seh is not None else BACKEND / "data/seh_kras_2009.json"
        self.corpus, self.timeout, self.cache_seconds = corpus, timeout, cache_seconds
        if self.fiches is not None and corpus:
            raise ValueError("Le filtre corpus nécessite la source PostgreSQL.")
        self._lock = threading.Lock()
        self._cached = None

    def info(self):
        seh = json.loads(self.seh.read_text(encoding="utf-8"))
        return {"exemple": seh["enonce"], "questions": [{"id": seh["seh_id"], "question": seh["enonce"]}],
                "source": "fichier" if self.fiches is not None else "postgres",
                "donnees_fictives": self.fiches == (BACKEND / "data/fiches_essais_fictives.json"),
                "backend": "Backend/matcher.py"}

    def _bundle(self, text):
        info = self.info()
        normalise = lambda s: " ".join(s.casefold().split()).rstrip(" ?.!…")
        if normalise(text) not in (normalise(info["exemple"]), normalise(info["questions"][0]["id"])):
            raise ValueError("Question non prise en charge : choisissez l'hypothèse proposée. "
                             "Le backend attend une SEH structurée et ne traduit pas les questions libres.")
        paths = [self.seh, BACKEND / ".env", ROOT / ".env"] + ([self.fiches] if self.fiches else [])
        stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in paths)
        with self._lock:
            if self._cached is not None:
                cached_stamp, at, payload = self._cached
                if cached_stamp == stamp and time.monotonic() - at < self.cache_seconds:
                    return payload
            with tempfile.TemporaryDirectory(prefix="trialrevive-front-") as folder:
                out = Path(folder) / "result.json"
                command = [sys.executable, str(ROOT / "frontend_matcher_worker.py"), "--seh", str(self.seh), "--sortie", str(out)]
                if self.fiches is not None:
                    command += ["--fiches", str(self.fiches)]
                if self.corpus:
                    command += ["--corpus", self.corpus]
                try:
                    proc = subprocess.run(command, cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    raise BackendUnavailable("Le backend a dépassé le délai d'analyse ; vérifiez la connexion et le volume du corpus.") from None
                try:
                    payload = json.loads(out.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    raise BackendUnavailable("Le backend n'a pas renvoyé de résultat lisible. Vérifiez ses dépendances.") from None
                if proc.returncode != 0 or "error" in payload:
                    raise BackendUnavailable(payload.get("error") or "Le backend n'a pas terminé l'analyse.")
            self._cached = stamp, time.monotonic(), payload
            return payload

    def analyze(self, text):
        bundle = self._bundle(text)
        info = self.info()
        d = adapt_result(bundle, source=info["source"], fictitious=info["donnees_fictives"])
        return {"dossier": d, "markdown": to_markdown(d), "exemple": info["exemple"], "resultat_backend": bundle["resultat"]}

    @staticmethod
    def comparison_rows(d, record):
        matched = compare.same_question(d["question"], record["question"])
        ours = ["Non calculé : pas de comptage individuel S0–S4", "Sources des fiches ; validation scientifique à effectuer",
                f"{len(d['ecartes'])} exclusions motivées, {len(d['a_completer'])} fiches à compléter, {len(d['en_cours'])} essais en cours"]
        return [{"Critère": title, "TrialRevive": ours[i] if matched else "Non évalué sur cette question",
                 "IA généraliste (évaluation déclarée)": record.get(key) or "Non évalué"}
                for i, (key, title) in enumerate(compare.CRITERIA.items())]

    def audit_nct(self, answer, text):
        fiches = self._bundle(text)["fiches"]
        available = {f.get("nct_id"): f for f in fiches if f.get("nct_id")}
        return [{"NCT cité": nct, "Cache local": "Présent dans les fiches chargées" if nct in available else "Absent des fiches (existence non déterminée)",
                 "Titre du registre": available[nct].get("titre") if nct in available else "À vérifier",
                 "Lien": f"https://clinicaltrials.gov/study/{nct}"}
                for nct in sorted({v.upper() for v in re.findall(r"\bNCT\d{8}\b", answer, flags=re.I)})]
