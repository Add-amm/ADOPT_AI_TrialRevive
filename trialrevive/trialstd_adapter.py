"""Adaptateur trialstd -> moteur TrialRevive (matcher.py, étages 1, 2 et 4).

matcher.py et stats.py ne sont pas modifiés. Cet adaptateur :
  1. traduit une hypothèse standardisée (schéma trialstd 1.0) en fiche de question (SEH) ;
  2. traduit chaque essai standardisé en fiche d'essai ;
  3. appelle matcher.apparier() tel quel ;
  4. remet le résultat sous la forme d'un classement unique (interface du banc d'essai, section 6),
     avec la raison de chaque verdict et des citations exactes du registre.

Les données standardisées viennent de l'une de ces sources, au contenu identique :
  - Supabase, projet « Trial Survive », schéma trialstd : variable TRIALSTD_PG_DSN (psycopg requis) ;
  - SQLite : standardization/output/trialstd.sqlite (mêmes tables) ;
  - fichiers du banc d'essai : bench/standardized/{hypotheses,trials}/.

Usage :
  python trialstd_adapter.py test_sami_Q001 --sqlite /mnt/project-files/standardization/output/trialstd.sqlite
  TRIALSTD_PG_DSN=postgresql://... python trialstd_adapter.py test_sami_Q001 --supabase

Ce que le registre ne dit pas (taux d'événements, couverture prévue quand un prélèvement est décrit)
est rempli par les valeurs de DEFAUTS ci-dessous, et chaque valeur par défaut est écrite dans la
raison de l'essai. Un essai sans aucun prélèvement décrit reste « à compléter », comme le prévoit le
moteur. Rien ici ne vient d'une IA ni d'une publication postérieure à la date de coupure.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sqlite3
import sys
import threading
import unicodedata
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import matcher  # noqa: E402
import stats  # noqa: E402

VERSION = "1.0"

# ---------------------------------------------------------------- valeurs par défaut (toutes affichées)
DEFAUTS = {
    # effets attendus pour le calcul de puissance de l'interaction : bénéfice net chez les X+, aucun chez
    # les X- ; valeur générique, pas tirée d'une publication postérieure à la date de coupure
    "hr_x_plus": 0.5,
    "hr_x_moins": 1.0,
    "prevalence_x": 0.4,          # si l'hypothèse ne donne pas de prévalence attendue
    "alpha": 0.05,
    "puissance": 0.80,
    "couverture_obligatoire": 0.9,  # prélèvement exigé à l'inclusion (critère d'éligibilité ou obligatoire)
    "couverture_facultative": 0.8,  # prélèvement décrit mais facultatif (consentement à part)
    "taux_evenements": {"advanced": 0.75, "early": 0.30, "autre": 0.50},
    "jours_archive": 3650,        # un tissu archivé jusqu'à 10 ans avant la première dose
}

# contraste de l'hypothèse pour lequel le bras contrôle ne doit pas recevoir la classe
SANS_CLASSE = {"without_class", "placebo", "bsc", "observation", "standard_of_care", "active_other", "add_on",
               "no_drug", "non_drug", "unknown", None}
SETTING_VERS_STADE = {"advanced": "metastatique", "early": "local"}
TISSU = {"tissue_ffpe", "tissue", "tissue_frozen", "slide"}
COMPATIBLES = {  # matériel demandé par l'hypothèse -> matériels qui permettent la mesure
    "tissue_ffpe": TISSU, "tissue": TISSU, "tissue_frozen": TISSU, "slide": {"slide", "tissue_ffpe", "tissue"},
    "plasma": {"plasma", "serum"}, "serum": {"serum", "plasma"}, "blood": {"blood", "plasma", "serum"},
    "germline_dna": {"germline_dna", "blood", "saliva"},
}
# biomarqueur exigé à l'inclusion -> matériel forcément analysé avant traitement
MATERIEL_DU_CRITERE = {"expression": "tissue", "somatic_alteration": "tissue", "genomic_signature": "tissue",
                       "circulating_analyte": "blood", "cell_count": "blood", "serostatus": "serum",
                       "germline_genotype": "germline_dna"}
DUREE_EVENEMENT = {"PFS", "TTP", "DFS", "EFS", "OS", "MACE", "DOR", "INFECTION_EFFICACY", "THROMBOSIS", "HOSPITALIZATION"}
EFFICACITE_AUTRE = {"ORR", "DCR", "PCR", "EXACERBATION", "LUNG_FUNCTION", "VIROLOGIC_RESPONSE", "IMMUNOGENICITY",
                    "LIPID_CHANGE", "GLYCEMIC", "BLOOD_PRESSURE", "SYMPTOMS", "QOL", "BLEEDING"}
CONSENTEMENT = {"broad": "biomarqueurs", "optional": "biomarqueurs", "restricted": "restreint"}

# Le registre ne donne pas l'effectif des essais en cours à la date de coupure, ni toujours les critères de
# jugement des anciens enregistrements : sans ces champs, l'étage 2 planterait (effectif) ou écarterait l'essai
# pour une information absente (critères). Pendant l'appel au moteur, on les ajoute donc aux champs « à compléter »
# (liste matcher.CHAMPS_ETAGE2, remise en l'état ensuite : importer l'adaptateur ne change pas le moteur).
CHAMPS_EN_PLUS = ("effectif_randomise", "criteres")
_VERROU = threading.RLock()


@contextmanager
def _champs_a_completer():
    with _VERROU:
        avant = list(matcher.CHAMPS_ETAGE2)
        matcher.CHAMPS_ETAGE2.extend(c for c in CHAMPS_EN_PLUS if c not in avant)
        try:
            yield
        finally:
            matcher.CHAMPS_ETAGE2[:] = avant


# ---------------------------------------------------------------- petits outils
def _jeton(x: str) -> str:
    return f"|{str(x).strip().lower()}|"


def _date(x: str | None) -> str | None:
    if not x:
        return None
    x = str(x)
    return x if len(x) >= 10 else (x + "-01" if len(x) == 7 else x + "-01-01" if len(x) == 4 else None)


def _court(t: str, n: int = 160) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def _norm(s: str) -> str:
    """Même normalisation que le banc d'essai pour vérifier qu'une citation est exacte."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def _nom(x: dict) -> str:
    return str(x.get("name") or x.get("id") or "").lower()


# formes de sel ou d'hydrate : « inclisiran sodium » est la molécule « inclisiran »
SELS = {"sodium", "disodium", "potassium", "calcium", "magnesium", "hydrochloride", "dihydrochloride", "hcl",
        "mesylate", "dimesylate", "besylate", "tosylate", "ditosylate", "maleate", "dimaleate", "fumarate",
        "succinate", "citrate", "tartrate", "acetate", "phosphate", "sulfate", "bromide", "chloride", "malate",
        "lactate", "meglumine", "tromethamine", "trometamol", "hydrate", "monohydrate", "dihydrate"}


def _base(nom: str) -> str:
    mots = str(nom).lower().split()
    while len(mots) > 1 and mots[-1] in SELS:
        mots.pop()
    return " ".join(mots)


def _contraste(t: dict) -> dict:
    return (t.get("design") or {}).get("contrast") or {}


def _textes(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _textes(v)
    elif isinstance(x, list):
        for v in x:
            yield from _textes(v)


# ---------------------------------------------------------------- contexte de l'hypothèse
class Contexte:
    """Ce que l'hypothèse standardisée dit de la molécule, de la classe et de la cible."""

    def __init__(self, h: dict, essais: list[dict]):
        n = h.get("normalized") or {}
        drogues = [d for d in n.get("drugs") or [] if d.get("kind", "drug") == "drug"]
        self.ids = {d["id"] for d in drogues if d.get("id")}
        self.noms = {d["name"].lower() for d in drogues if d.get("name")} | {x.lower() for x in h.get("drug") or []}
        cites = [d["name"].lower() for d in drogues if d.get("source") == "text"]
        self.ideales = sorted(set(cites)) or sorted(self.noms)
        cur = [c for c in n.get("drug_classes") or []
               if c.get("source") == "curated" and c.get("id") and not c["id"].startswith("cls:chemo")]
        if cur:
            self.classes = {c["id"] for c in cur}
            self.libelle = " / ".join(dict.fromkeys(c.get("label") or c["id"] for c in cur))
            self.libelles = {c["label"].lower() for c in cur if c.get("label")}
        else:  # pas de classe éditée : celles des molécules de l'hypothèse (ChEMBL), sinon aucune
            propres = [c for d in drogues for c in d.get("classes") or []
                       if c.get("id") and not c["id"].startswith("cls:chemo")]
            self.classes = {c["id"] for c in propres}
            self.libelles = {c["label"].lower() for c in propres if c.get("label")}
            noms = ", ".join(self.ideales) or "?"
            self.libelle = f"molécule de l'hypothèse ({noms})"
        self.cibles = {t["symbol"] for t in n.get("targets") or [] if t.get("symbol")}
        # molécule inconnue des ontologies (ex. molécule fictive) : la cible se lit dans les essais qui la testent,
        # quand ils excluent un traitement antérieur « par inhibiteur de <cible> »
        if drogues and all(not d.get("classes") and not d.get("targets") for d in drogues):
            for t in essais:
                diff = {str(x).lower() for x in (_contraste(t).get("differential_drugs") or [])}
                if diff & self.noms:
                    for p in (t.get("population") or {}).get("prior_therapy_excluded") or []:
                        if p.get("class_target"):
                            self.cibles.add(p["class_target"])
        self.bios = n.get("biomarkers") or []

    def membre(self, d: dict, t: dict) -> str | None:
        """Comment une intervention de l'essai appartient à la classe de l'hypothèse (None sinon)."""
        if d.get("kind", "drug") != "drug":
            return None
        nom = (d.get("name") or "").lower()
        if (d.get("id") and d["id"] in self.ids) or nom in self.noms or _base(nom) in self.noms:
            return "molécule"
        cls = d.get("classes") or []
        if {c.get("id") for c in cls} & self.classes or {(c.get("label") or "").lower() for c in cls} & self.libelles:
            return "classe"
        if not d.get("classes") and not d.get("targets") and self.cibles:
            exclues = {p.get("class_target") for p in (t.get("population") or {}).get("prior_therapy_excluded") or []}
            diff = {str(x).lower() for x in (_contraste(t).get("differential_drugs") or [])}
            if exclues & self.cibles and (d.get("name") or "").lower() in diff:
                return "classe déduite"
        return None


# ---------------------------------------------------------------- hypothèse -> fiche de question (SEH)
def _jour_ideal(phrase: str) -> int | None:
    m = re.search(r"\b(?:day|jour|j|d)\s?(\d{1,3})\b", phrase or "", re.I)
    if m:
        return int(m.group(1)) - 1  # jour 1 = jour de la première dose
    m = re.search(r"\b(?:week|semaine|w)\s?(\d{1,2})\b", phrase or "", re.I)
    return 7 * int(m.group(1)) if m else None


def _instant_hypothese(materiel: dict) -> tuple[list[int], int]:
    kind, moment = materiel.get("kind"), materiel.get("moment")
    if moment == "on":
        j = _jour_ideal(materiel.get("phrase") or "")
        return ([j - 7, j + 7], 7) if j is not None else ([1, 365], 30)
    if moment == "post":
        return [1, DEFAUTS["jours_archive"]], 30
    if kind in TISSU or kind == "germline_dna" or moment is None:
        return [-DEFAUTS["jours_archive"], -1], 30  # marqueur stable : un tissu ou un ADN archivé convient
    return [-30, -1], 30  # marqueur qui varie (sang) : mesure de début de traitement


def _criteres_hypothese(codes: list[str]) -> dict:
    duree = [c for c in codes if c in DUREE_EVENEMENT]
    if duree:
        ideal = duree
        table = {c: 1.0 for c in ideal} | {c: 0.9 for c in DUREE_EVENEMENT if c not in ideal}
        substituts = sorted(EFFICACITE_AUTRE)
    else:
        ideal = list(codes) or ["OS"]
        table = {c: 1.0 for c in ideal}
        substituts = sorted((DUREE_EVENEMENT | EFFICACITE_AUTRE) - set(ideal))
    return {"champ": "critere", "niveau": "tolere", "ideal": {"valeurs": ideal},
            "tolere": {"valeurs": [c for c, s in table.items() if s < 1]},
            "substitut": {"valeurs": substituts, "score": 0.6, "plafond_preuve": "E2"},
            "table_substitution": table, "plafond_preuve": None, "regle": "TOL-CRITERE-v1 (adaptateur)"}


def seh_depuis_hypothese(h: dict, ctx: Contexte, molecules_vues: set[str]) -> dict:
    n = h.get("normalized") or {}
    ind = n.get("indication") or {}
    prev = (n.get("expected_prevalence") or {}).get("value")
    if prev is None:
        prev = h.get("expected_prevalence")
    prev_defaut = prev is None
    prev = min(max(float(prev if prev is not None else DEFAUTS["prevalence_x"]), 0.02), 0.98)
    bio = (n.get("biomarkers") or [{}])[0]
    nom_bio = (bio.get("label") or h.get("biomarker") or "biomarqueur").split()[0]
    inclut = [_jeton(x) for x in ind.get("labels") or []] + [_jeton(d["id"]) for d in ind.get("diseases") or [] if d.get("id")]
    if not inclut:
        inclut = [_jeton(ind.get("text") or h.get("indication") or "?")]
    stade = SETTING_VERS_STADE.get(h.get("setting") or ind.get("setting"))
    comp = (n.get("comparator") or {}).get("type")
    materiel = n.get("material") or {}
    kind = materiel.get("kind")
    intervalle, limite = _instant_hypothese(materiel)
    table = {m: 1.0 for m in ctx.ideales} | {m: 0.8 for m in sorted(molecules_vues) if m not in ctx.ideales}
    return {
        "seh_id": h.get("id"), "version": 1, "statut": f"généré par trialstd_adapter {VERSION} (à valider)",
        "valide_par": None, "type_hypothese": "predictive", "enonce": h.get("free_text"),
        "date_hypothese": h.get("cutoff_date"),
        "source": {"doc": "hypothèse standardisée trialstd " + str(h.get("id")), "passage": h.get("free_text")},
        "biomarqueur_x": f"{nom_bio} ({bio.get('id') or 'id inconnu'})",
        "effets_attendus": {"hr_x_plus": DEFAUTS["hr_x_plus"], "hr_x_moins": DEFAUTS["hr_x_moins"], "prevalence_x": prev},
        "exigence_statistique": {"alpha": DEFAUTS["alpha"], "puissance": DEFAUTS["puissance"]},
        "defauts": ([f"prévalence attendue inconnue : {DEFAUTS['prevalence_x']:.0%} par défaut"] if prev_defaut else [])
                   + [f"effets attendus par défaut : HR {DEFAUTS['hr_x_plus']} chez les X+, {DEFAUTS['hr_x_moins']} chez les X-"],
        "contraintes": [
            {"champ": "indication", "niveau": "obligatoire", "valeur": {"inclut": inclut, "stade": stade}},
            {"champ": "date_debut", "niveau": "obligatoire", "valeur": {"avant": h.get("cutoff_date")},
             "explication": "état du monde figé à la date de l'hypothèse"},
            {"champ": "comparateur", "niveau": "obligatoire",
             "valeur": {"randomise": True, "exclut_classe": ctx.libelle if comp in SANS_CLASSE else None}},
            {"champ": "traitement", "niveau": "tolere", "ideal": {"molecules": ctx.ideales},
             "tolere": {"classe": ctx.libelle}, "table_substitution": table, "plafond_preuve": "E3",
             "regle": "TOL-MOLECULE-v1"},
            _criteres_hypothese((n.get("outcomes") or {}).get("codes") or h.get("outcomes") or []),
            {"champ": "materiel", "niveau": "obligatoire",
             "valeur": {"types": sorted(COMPATIBLES.get(kind, {kind} if kind else TISSU | {"blood", "plasma", "serum", "germline_dna"}))}},
            {"champ": "instant", "niveau": "tolere", "ideal": {"ancrage": "premiere_dose", "intervalle_j": intervalle},
             "fonction_tolerance": {"type": "lineaire_distance", "limite_j": limite}, "plafond_preuve": None,
             "regle": "TOL-TEMPS-v1 (adaptateur)"},
            {"champ": "presence_deux_bras", "niveau": "obligatoire", "valeur": True},
            {"champ": "couverture", "niveau": "tolere", "ideal": {"min": 0.80}, "tolere": {"min": 0.60},
             "plafond_preuve": "E2", "regle": "TOL-COUV-v1"},
            {"champ": "consentement", "niveau": "tolere", "ideal": {"valeurs": ["biomarqueurs"]},
             "tolere": {"valeurs": ["inconnu"]}, "table_substitution": {"biomarqueurs": 1.0, "inconnu": 0.7},
             "plafond_preuve": None, "regle": "TOL-CONSENT-v1"},
        ],
    }


# ---------------------------------------------------------------- essai standardisé -> fiche d'essai
def _instant_essai(it: dict) -> list[int]:
    jour, fen, moment = it.get("day"), it.get("window_days") or 0, it.get("moment")
    if moment == "pre" and (jour is None or jour <= 1):
        return [-DEFAUTS["jours_archive"], -1] if it.get("material") in TISSU else [-28, -1]
    if jour is not None:
        return [jour - 1 - fen, jour - 1 + fen]
    if moment == "on":
        return [1, 180]
    if moment == "post":
        return [181, DEFAUTS["jours_archive"]]
    return [-DEFAUTS["jours_archive"], -1] if it.get("material") in TISSU else [-28, -1]


def _prelevements(t: dict) -> list[dict]:
    s = t.get("samples") or {}
    items = [dict(it, _derive=None) for it in s.get("items") or [] if it.get("purpose") in (None, "biomarker")]
    if s.get("pre_treatment_tissue") and not any(it.get("material") in TISSU for it in items):
        items.append({"material": "tissue", "moment": "pre", "mandatory": None, "field": None, "quote": None,
                      "_derive": "tissu avant traitement signalé par le standardiseur"})
    vus = {it.get("material") for it in items}
    for b in t.get("biomarkers") or []:
        mat = MATERIEL_DU_CRITERE.get(b.get("kind"))
        if mat and "eligibility_inclusion" in (b.get("roles") or []) and mat not in vus:
            ev = next((e for e in b.get("evidence") or [] if e.get("field") == "eligibility_inclusion"), None)
            items.append({"material": mat, "moment": "pre", "mandatory": True, "field": "eligibility_inclusion",
                          "quote": (ev or {}).get("quote"),
                          "_derive": f"{b.get('label') or b.get('id')} exigé à l'inclusion : mesuré avant traitement"})
            vus.add(mat)
    return items


def fiche_depuis_essai(t: dict, ctx: Contexte, seh_materiels: set[str]) -> dict:
    d, ind, s, dates = t.get("design") or {}, t.get("indication") or {}, t.get("samples") or {}, t.get("dates") or {}
    defauts, membres = [], {}
    canon = lambda nom: _base(nom) if _base(nom) in ctx.noms else str(nom).lower()
    for x in t.get("interventions") or []:
        how = ctx.membre(x, t)
        if how and _nom(x):
            membres[canon(_nom(x))] = how
    # la classe de l'hypothèse n'est déclarée que par ses molécules (sinon l'étage 2 n'aurait aucune molécule)
    autres = sorted({c.get("label") or c.get("id") or "?" for x in t.get("interventions") or []
                     for c in x.get("classes") or [] if canon(_nom(x)) not in membres} - {ctx.libelle})[:4]

    def classes_bras(a: dict) -> list[str]:
        noms = {str(x).lower() for x in a.get("drugs") or []}
        ids = set(a.get("drug_ids") or [])
        dans_bras = {canon(x) for x in noms} & set(membres)
        placebo = a.get("role") == "placebo_comparator" or "placebo" in (a.get("controls") or [])
        if placebo:
            # « BKM120/placebo » attribué aux deux bras : un bras placebo ne reçoit pas la molécule qu'il imite,
            # sauf si son libellé la nomme (molécule de fond, ex. « Placebo + trastuzumab »)
            lib = (a.get("label") or "").lower()
            dedans = any(x in lib for x in dans_bras)
        else:
            dedans = bool(dans_bras) or bool(ids & ctx.ids) or bool(set(a.get("classes") or []) & ctx.classes)
        return ([ctx.libelle] if dedans else []) + sorted(set(a.get("classes") or []) - ctx.classes)[:3]

    bras, vus = [], set()
    for i, a in enumerate(d.get("arms") or []):
        nom = a.get("label") or f"bras {i + 1}"
        if nom in vus:
            nom = f"{nom} ({i + 1})"
        vus.add(nom)
        bras.append({"nom": nom, "n": None, "role": a.get("role"), "interventions": a.get("drugs") or [],
                     "classes": classes_bras(a)})
    controles = [b for b in bras if ctx.libelle not in b["classes"]]
    if not bras:  # registre sans bras : la classe est dans le bras contrôle si elle fait partie du traitement de fond
        fond = {canon(x) for x in _contraste(t).get("background_drugs") or []}
        controles_classes = [ctx.libelle] if fond & set(membres) else []
    else:
        controles_classes = sorted({c for b in controles for c in b["classes"]})

    # date de début : celle du registre, sinon (essai pas encore commencé) après la date de coupure,
    # sinon la date de première publication
    debut = _date(dates.get("start"))
    if not debut:
        if dates.get("status_at_cutoff") == "not_started":
            debut = "9999-12-31"
        else:
            debut = _date(dates.get("first_posted")) or "9999-12-31"
            defauts.append("date de début absente du registre : date de première publication")

    # critères de jugement : primaires d'abord, puis secondaires
    out = t.get("outcomes") or {}
    codes = list(dict.fromkeys([c for c in out.get("primary_codes") or [] if c in DUREE_EVENEMENT | EFFICACITE_AUTRE]
                               + [c for c in out.get("codes") or [] if c in DUREE_EVENEMENT | EFFICACITE_AUTRE]))

    # prélèvements, couverture prévue, consentement
    items = _prelevements(t)
    noms_bras = [b["nom"] for b in bras]
    prelevements = [{"materiel": it.get("material"), "instant_j": _instant_essai(it), "bras": noms_bras,
                     "statut": "prevu", "obligatoire": bool(it.get("mandatory") or str(it.get("field") or "").startswith("eligibility")),
                     "citation": it.get("quote"), "deduit": it.get("_derive")} for it in items] or None
    couverture = None
    if prelevements:
        utiles = [p for p in prelevements if p["materiel"] in seh_materiels] or prelevements
        couverture = DEFAUTS["couverture_obligatoire"] if any(p["obligatoire"] for p in utiles) else DEFAUTS["couverture_facultative"]
        defauts.append(f"couverture prévue {couverture:.0%} ({'prélèvement exigé' if couverture == DEFAUTS['couverture_obligatoire'] else 'prélèvement facultatif'}, valeur par défaut)")
    effectif = d.get("enrollment") if isinstance(d.get("enrollment"), (int, float)) and d.get("enrollment") > 0 else None
    evenements = s.get("events_primary_analysis")
    if effectif and isinstance(evenements, (int, float)) and evenements > 0:
        taux = min(evenements / effectif, 1.0)
    else:
        cadre = ind.get("setting") if ind.get("setting") in ("advanced", "early") else "autre"
        taux = DEFAUTS["taux_evenements"][cadre]
        defauts.append(f"taux d'événements {taux:.0%} (valeur par défaut, cadre {cadre})")
    consent = CONSENTEMENT.get(s.get("consent"), "inconnu")

    mesures = []
    cles = {b.get("key"): (b.get("label") or b.get("id") or "?").split()[0] for b in ctx.bios if b.get("key")}
    for b in t.get("biomarkers") or []:
        if b.get("key") in cles and b.get("kind") != "drug_target" and \
                set(b.get("roles") or []) & {"measured", "stratification", "eligibility_inclusion", "population"}:
            mesures.append(cles[b["key"]])

    src = lambda champ, q=None: {"doc": f"ClinicalTrials.gov {t['id']} (vue à la date de coupure, trialstd)", "passage": q or champ}
    return {
        "trial_id": t["id"], "index": "interne" if s.get("holder") == "internal" else "externe",
        "titre": (t.get("identity") or {}).get("title"), "detenteur": (t.get("identity") or {}).get("sponsor"),
        "date_debut": debut,
        "indication": " ; ".join(ind.get("conditions") or []) + " || "
                      + " ".join(_jeton(x) for x in (ind.get("labels") or []))
                      + " " + " ".join(_jeton(dd.get("id") or "") + " " + _jeton(dd.get("name") or "") for dd in ind.get("diseases") or [])
                      + " " + " ".join(_jeton(a) for dd in ind.get("diseases") or [] for a in dd.get("ancestors") or []),
        "stade": SETTING_VERS_STADE.get(ind.get("setting")),
        "randomise": d.get("randomized") is True,
        "traitement": {"molecules": sorted(membres), "classes": ([ctx.libelle] if membres else []) + autres,
                       "classe": ctx.libelle if membres else None},
        "comparateur": {"description": "; ".join(b["nom"] for b in controles) or None, "classes": controles_classes},
        "effectif_randomise": int(effectif) if effectif else None,
        "bras": bras or None,
        "criteres": codes or None,
        "prelevements": prelevements, "taux_collecte_prevu": couverture,
        "taux_evenements_prevu": round(taux, 3), "consentement_portee": consent,
        "biomarqueurs_mesures": sorted(set(mesures)),
        "phases": d.get("phases") or [],
        "sources": {"design": src("designModule"), "bras": src("armsInterventionsModule"),
                    "criteres": src("outcomesModule"), "date_debut": src("statusModule"),
                    "prelevements": src("descriptionModule / eligibilityModule")},
        "confiance": {"registre": 0.9, "valeurs_par_defaut": 0.0},
        # champs propres à l'adaptateur (ignorés par le moteur)
        "_statut": dates.get("status_at_cutoff"), "_membres": membres, "_defauts": defauts,
        "_acronyme": (t.get("identity") or {}).get("acronym"),
    }


# ---------------------------------------------------------------- orchestration
def apparier_standardise(h: dict, essais: list[dict]) -> tuple[dict, list[dict], dict]:
    """Hypothèse et essais standardisés -> (fiche de question, fiches d'essai, résultat brut du moteur)."""
    ctx = Contexte(h, essais)
    kind = ((h.get("normalized") or {}).get("material") or {}).get("kind")
    seh_materiels = COMPATIBLES.get(kind, {kind} if kind else TISSU)
    fiches = [fiche_depuis_essai(t, ctx, seh_materiels) for t in essais]
    vues = {m for f in fiches for m in f["traitement"]["molecules"]}
    seh = seh_depuis_hypothese(h, ctx, vues)
    with _champs_a_completer():
        res = matcher.apparier(seh, fiches)
    return seh, fiches, res


def _raison_lisible(r: str, f: dict) -> str:
    """Les raisons du moteur, sans les jetons techniques que l'adaptateur ajoute à l'indication."""
    if r.startswith("indication hors champ"):
        return f"indication hors champ ({_court(f['indication'].split(' || ')[0], 80) or 'non précisée'})"
    if "9999-12-31" in r:
        return "essai pas encore commencé à la date de coupure (aucune date de début)"
    return r


def _phase(f: dict) -> int:
    ph = [int(m) for p in f.get("phases") or [] for m in re.findall(r"\d", str(p))]
    return max(ph) if ph else 0


def _provisoire(seh: dict, f: dict) -> tuple:
    """Rejoue l'étage 2 du moteur sur une copie de la fiche dont les champs manquants sont remplis par des valeurs
    prudentes (prélèvement du matériel demandé à la couverture minimale tolérée, critère toléré, effectif ignoré).
    Sert seulement à classer entre elles les fiches à compléter et les essais en cours ; le verdict ne change pas."""
    g = json.loads(json.dumps(f, default=str))
    if not g["traitement"]["molecules"]:
        return (0, 0, 0.0, 0)
    c = {x["champ"]: x for x in seh["contraintes"]}
    lib = c["traitement"]["tolere"]["classe"]
    if not g.get("bras"):
        g["bras"] = [{"nom": "expérimental", "classes": [lib]}, {"nom": "contrôle", "classes": []}]
    noms = [b["nom"] for b in g["bras"]]
    if not g.get("prelevements"):
        g["prelevements"] = [{"materiel": c["materiel"]["valeur"]["types"][0],
                              "instant_j": c["instant"]["ideal"]["intervalle_j"], "bras": noms}]
        g["taux_collecte_prevu"] = c["couverture"]["tolere"]["min"]
    for pr in g["prelevements"]:
        if not pr.get("bras"):
            pr["bras"] = noms
    if g.get("taux_collecte_prevu") is None:
        g["taux_collecte_prevu"] = c["couverture"]["tolere"]["min"]
    if not g.get("criteres"):
        tol = [k for k, v in c["critere"]["table_substitution"].items() if v < 1]
        g["criteres"] = tol[:1] or c["critere"]["ideal"]["valeurs"][:1]
    if not g.get("effectif_randomise"):
        g["effectif_randomise"] = 10 ** 6
    ok, score, plafond, bonus, _, details = matcher.etage2(seh, g)
    if not ok:
        return (0, 0, 0.0, 0)
    niveau = matcher.etage4(seh, g, plafond, details)["niveau_preuve_atteignable"]
    return (1, matcher.niv(niveau), score, bonus)


def _tri_niveau1(prov: tuple, f: dict, manquants: list, en_cours: bool) -> tuple:
    """Ordre des essais en cours et des fiches à compléter (le moteur ne les classe pas)."""
    ok, niveau, score, bonus = prov
    return (-ok, -niveau, -score, -bonus, -_phase(f), -(f["effectif_randomise"] or 0))


def _cle_moteur(r: dict):
    return (matcher.niv(r["niveau_preuve_atteignable"]), r["score_compatibilite"], r["bonus_ideal"], r["effectif_randomise"])


def _citations(t: dict, f: dict, texte: str | None) -> list[dict]:
    """Citations exactes du registre : titre, bras, prélèvement retenu."""
    cands = [("title", (t.get("identity") or {}).get("title"))]
    for a in (t.get("design") or {}).get("arms") or []:
        ev = a.get("evidence") or {}
        cands.append((ev.get("field") or "arms", ev.get("quote")))
    for p in f.get("prelevements") or []:
        cands.append(("samples", p.get("citation")))
    out, vus = [], set()
    for champ, q in cands:
        if not q or len(q) < 12 or q in vus:
            continue
        if texte is not None and _norm(q) not in texte:
            continue
        vus.add(q)
        out.append({"source": "ctgov", "id": t["id"], "url": f"https://clinicaltrials.gov/study/{t['id']}",
                    "field": champ, "quote": q})
        if len(out) >= 4:
            break
    return out


def classement(h: dict, essais: list[dict], textes: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """Classement unique pour le banc d'essai (meilleur d'abord) et résultat complet du moteur.

    Ordre : retenus par le moteur (clé du moteur : niveau, score, bonus, effectif ; internes et externes
    fusionnés pour le banc) ; puis essais non terminés à la date de coupure et fiches à compléter ; puis
    écartés à l'étage 2 ; puis écartés à l'étage 1 (moins de raisons d'abord, molécule de la classe d'abord).
    """
    seh, fiches, res = apparier_standardise(h, essais)
    par_id = {f["trial_id"]: f for f in fiches}
    essai_par_id = {t["id"]: t for t in essais}
    en_cours = lambda tid: par_id[tid]["_statut"] in ("ongoing", "not_started")
    lignes = []  # (tier, clé de tri, élément)

    retenus = sorted(res["internes"] + res["externes"], key=lambda r: (_cle_moteur(r), r["index"] == "interne"), reverse=True)
    for k, r in enumerate(retenus):
        f = par_id[r["trial_id"]]
        pw = r["puissance_a_priori"]
        ev = pw["evenements_attendus"]
        verdict = "ongoing" if en_cours(r["trial_id"]) else "retained"
        texte = (f"Retenu par le moteur (étage 4) : niveau de preuve atteignable {r['niveau_preuve_atteignable']}, "
                 f"voie {r['voie']['code']}, score de compatibilité {r['score_compatibilite']}, puissance a priori de "
                 f"l'interaction {pw['valeur']:.0%} ({ev['x_plus'] + ev['x_moins']} événements attendus). "
                 f"Molécule(s) de la classe : {', '.join(f['traitement']['molecules'])} ({', '.join(sorted(set(f['_membres'].values())))}).")
        if r["ecarts"]:
            texte += " Écarts : " + " ; ".join(r["ecarts"]) + "."
        if verdict == "ongoing":
            texte += " Essai non terminé à la date de coupure : il pourra répondre à son analyse principale."
        tri = (0, k) if verdict == "retained" else _tri_niveau1((1,) + _cle_moteur(r)[:3], f, [], True)
        lignes.append((0 if verdict == "retained" else 1, tri, r["trial_id"], verdict, texte, 4, "reanalysis_candidate"))

    for x in res["a_completer"]:
        f = par_id[x["trial_id"]]
        verdict = "ongoing" if en_cours(x["trial_id"]) else "borderline"
        texte = (f"Passe l'étage 1 (indication, date, essai randomisé, bras contrôle sans la classe, molécule "
                 f"{', '.join(f['traitement']['molecules'])}) ; fiche à compléter : {', '.join(x['champs_manquants'])}.")
        if verdict == "ongoing":
            texte += " Essai non terminé à la date de coupure."
        lignes.append((1, _tri_niveau1(_provisoire(seh, f), f, x["champs_manquants"], verdict == "ongoing"),
                       x["trial_id"], verdict, texte, 2, "reanalysis_candidate"))

    for x in res["exclus"]:
        f = par_id[x["trial_id"]]
        if x["etage"] == 2:
            cle = (-(f["effectif_randomise"] or 0),)
            texte = "Écarté à l'étage 2 : " + " ; ".join(x["raisons"]) + "."
            if x.get("ecarts_avant_exclusion"):
                texte += " Écarts déjà notés : " + " ; ".join(x["ecarts_avant_exclusion"]) + "."
            lignes.append((2, cle, x["trial_id"], "excluded", texte, 2, "supporting"))
        else:
            cle = (len(x["raisons"]), 0 if f["traitement"]["molecules"] else 1, -(f["effectif_randomise"] or 0))
            texte = "Écarté à l'étage 1 : " + " ; ".join(_raison_lisible(r, f) for r in x["raisons"]) + "."
            lignes.append((3, cle, x["trial_id"], "excluded", texte, 1, "supporting"))

    lignes.sort(key=lambda l: (l[0], l[1]))
    n = max(len(lignes), 1)
    items = []
    for i, (tier, _, tid, verdict, texte, etage, role) in enumerate(lignes):
        f, t = par_id[tid], essai_par_id[tid]
        if f["_defauts"] and tier < 3:
            texte += " Valeurs par défaut : " + " ; ".join(f["_defauts"]) + "."
        items.append({"nct_id": tid, "score": round(1 - i / n, 4), "verdict": verdict, "role": role,
                      "rationale": texte, "stage": etage,
                      "evidence": _citations(t, f, (textes or {}).get(tid) if textes is not None else None)})
    return items, {"seh": seh, "resultat_moteur": res}


def classer_pour_banc(hypothesis: dict, corpus: list[dict]) -> list[dict]:
    """Point d'entrée du banc d'essai : hypothesis['standardized'] et record['standardized'] (section 3b)."""
    h = hypothesis.get("standardized")
    if not h:
        raise ValueError("hypothèse standardisée absente : l'adaptateur lit hypothesis['standardized']")
    essais, sans = [], []
    textes = {}
    for rec in corpus:
        tid = ((rec.get("trialrevive") or {}).get("id") or (rec.get("standardized") or {}).get("id")
               or ((rec.get("protocolSection") or {}).get("identificationModule") or {}).get("nctId"))
        if rec.get("standardized"):
            essais.append(rec["standardized"])
            textes[tid] = _norm(" \n ".join(_textes(rec.get("protocolSection") or {})))
        else:
            sans.append(tid)
    items, _ = classement(h, essais, textes)
    for tid in sans:
        items.append({"nct_id": tid, "score": 0.0, "verdict": "excluded", "role": "supporting",
                      "rationale": "Pas de fiche standardisée pour cet essai : non examiné.", "evidence": []})
    return items


# ---------------------------------------------------------------- lecture des données standardisées
def corpus_de(hyp_id: str) -> str:
    return "sami_fictional.jsonl.gz" if hyp_id.startswith(("dev_sami_H", "test_sami_H")) else f"{hyp_id}.jsonl.gz"


def charger_sqlite(chemin: str, hyp_id: str, corpus: str) -> tuple[dict, list[dict]]:
    con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    h = json.loads(con.execute("select json from hypotheses where id = ?", (hyp_id,)).fetchone()[0])
    essais = [json.loads(j) for (j,) in con.execute("select json from trials where corpus = ? order by id", (corpus,))]
    return h, essais


def charger_supabase(dsn: str, hyp_id: str, corpus: str) -> tuple[dict, list[dict]]:
    try:
        import psycopg
    except ImportError:  # psycopg 2
        import psycopg2 as psycopg
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        cur.execute("select json from trialstd.hypotheses where id = %s", (hyp_id,))
        h = cur.fetchone()[0]
        cur.execute("select json from trialstd.trials where corpus = %s order by id", (corpus,))
        essais = [r[0] for r in cur.fetchall()]
    lire = lambda x: x if isinstance(x, dict) else json.loads(x)
    return lire(h), [lire(e) for e in essais]


def charger_banc(dossier: str, hyp_id: str, corpus: str) -> tuple[dict, list[dict]]:
    d = Path(dossier)
    h = json.loads((d / "hypotheses" / f"{hyp_id}.json").read_text(encoding="utf-8"))
    with gzip.open(d / "trials" / corpus, "rt", encoding="utf-8") as fh:
        essais = [json.loads(line) for line in fh]
    return h, essais


def resume_classement(items: list[dict], n: int = 20) -> str:
    lignes = [f"{'rang':>4}  {'essai':<16} {'verdict':<10} raison"]
    for i, it in enumerate(items[:n], 1):
        lignes.append(f"{i:>4}  {it['nct_id']:<16} {it['verdict']:<10} {_court(it['rationale'], 150)}")
    return "\n".join(lignes)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Moteur TrialRevive (matcher.py) sur les données standardisées trialstd")
    ap.add_argument("hypothese", help="identifiant de l'hypothèse standardisée (ex. test_sami_Q001)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--supabase", action="store_true", help="lire Supabase (variable TRIALSTD_PG_DSN)")
    src.add_argument("--sqlite", help="chemin de trialstd.sqlite")
    src.add_argument("--banc", help="dossier bench/standardized")
    ap.add_argument("--corpus", help="nom du corpus (défaut : déduit de l'identifiant)")
    ap.add_argument("--sortie", help="écrire fiche de question, résultat du moteur et classement (JSON)")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args(argv)
    corpus = a.corpus or corpus_de(a.hypothese)
    if a.supabase:
        dsn = os.environ.get("TRIALSTD_PG_DSN")
        if not dsn:
            raise SystemExit("TRIALSTD_PG_DSN absent (chaîne de connexion Supabase, bouton Connect du tableau de bord)")
        h, essais = charger_supabase(dsn, a.hypothese, corpus)
    elif a.banc:
        h, essais = charger_banc(a.banc, a.hypothese, corpus)
    else:
        h, essais = charger_sqlite(a.sqlite or "/mnt/project-files/standardization/output/trialstd.sqlite", a.hypothese, corpus)
    items, detail = classement(h, essais)
    print(matcher.resume(detail["resultat_moteur"]))
    print()
    print(resume_classement(items, a.top))
    if a.sortie:
        Path(a.sortie).write_text(json.dumps({"hypothese": a.hypothese, "corpus": corpus, "adaptateur": VERSION,
                                              "defauts": DEFAUTS, **detail, "classement": items},
                                             ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"\nRésultat complet : {a.sortie}")


if __name__ == "__main__":
    main()
