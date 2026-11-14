"""Transforme la base standardisée de l'équipe (schéma 1.0) en fiches d'essai pour matcher.py.

Entrées acceptées :
    un export CSV de la table `trials` (colonne `json`), un fichier .jsonl ou un corpus .jsonl.gz

Usage :
    python3 adaptateur_base.py trials_rows.csv --sortie data/fiches_base.json
    python3 adaptateur_base.py corpus.jsonl.gz --corpus kras --sortie data/fiches_base.json
    python3 matcher.py data/seh_kras_2009.json data/fiches_base.json resultat_base.json

Ce que la base ne donne pas est remplacé par une FOURCHETTE par défaut, marquée comme
hypothèse dans `sources` : part de patients avec échantillon et, si le nombre d'événements
est absent, taux d'événements. Ces valeurs sont des paramètres à valider (biologiste).
"""
import argparse
import csv
import gzip
import json
import re

# --- paramètres par défaut, à valider ------------------------------------------------
COUVERTURE_DEFAUT = [0.60, 0.90]                 # part de patients avec échantillon exploitable
TAUX_EVENEMENTS_DEFAUT = {"metastatique": [0.75, 0.95], "local": [0.20, 0.50], None: [0.30, 0.90]}
FENETRE_TISSU_J = [-3650, -1]                    # tissu archivé avant la première dose
# --------------------------------------------------------------------------------------

STADE = {"advanced": "metastatique", "early": "local"}
CONSENT = {"broad": "biomarqueurs", "optional": "optionnel", "restricted": "restreint"}
ROLE_EXP = {"experimental"}
CLASSES_CONNUES = {"cetuximab": "anti-EGFR", "panitumumab": "anti-EGFR",
                   "bevacizumab": "anti-VEGF", "aflibercept": "anti-VEGF"}
CRITERES = [(re.compile(r"pfs|progression", re.I), "PFS"), (re.compile(r"\bos\b|overall.?survival", re.I), "OS"),
            (re.compile(r"orr|response", re.I), "ORR")]


def lire(chemin):
    if chemin.endswith(".csv"):
        csv.field_size_limit(10 ** 9)
        for r in csv.DictReader(open(chemin, newline="")):
            yield json.loads(r["json"])
    else:
        ouvrir = gzip.open if chemin.endswith(".gz") else open
        with ouvrir(chemin, "rt") as f:
            for ligne in f:
                if ligne.strip():
                    yield json.loads(ligne)


def classes_de(medicaments, classes):
    """Classes de la base + rattachement des molécules connues à notre vocabulaire."""
    out = set(classes or [])
    for m in medicaments or []:
        for mol, cl in CLASSES_CONNUES.items():
            if mol in str(m).lower():
                out.add(cl)
    for c in list(out):
        if "egfr" in str(c).lower():
            out.add("anti-EGFR")
    return sorted(out)


def vers_fiche(j):
    ident, design, dates = j.get("identity", {}), j.get("design", {}), j.get("dates", {})
    ind, samples, contrast = j.get("indication", {}), j.get("samples", {}), design.get("contrast", {})
    tid = (j.get("trialrevive") or {}).get("id") or j.get("id")
    src, hyp = {}, []

    bras = []
    for a in design.get("arms") or []:
        bras.append({"nom": a.get("label"), "type": "EXPERIMENTAL" if a.get("role") in ROLE_EXP else "CONTROLE",
                     "n": None, "interventions": a.get("drugs") or [],
                     "classes": classes_de(a.get("drugs"), a.get("classes"))})
        if a.get("evidence"):
            src[f"bras:{a.get('label')}"] = {"doc": tid, "passage": a["evidence"].get("quote")}

    mols = [str(d).lower() for d in (contrast.get("differential_drugs") or [])] or \
           [str(d).lower() for b in bras if b["type"] == "EXPERIMENTAL" for d in b["interventions"]] or \
           [i.get("name", "").lower() for i in j.get("interventions") or [] if i.get("kind") in (None, "drug", "biological")]
    cl_exp = classes_de(mols, contrast.get("differential_classes"))
    cl_ctrl = sorted({c for b in bras if b["type"] != "EXPERIMENTAL" for c in b["classes"]})

    stade = STADE.get(ind.get("setting"))
    effectif = design.get("enrollment")
    evenements = samples.get("events_primary_analysis")

    # taux d'événements : observé si la base le donne, sinon fourchette par défaut
    if evenements and effectif:
        taux_evt = round(min(1.0, evenements / effectif), 3)
        src["taux_evenements_prevu"] = {"doc": tid, "passage": "samples.events_primary_analysis / design.enrollment"}
    else:
        taux_evt = TAUX_EVENEMENTS_DEFAUT[stade]
        hyp.append("taux_evenements_prevu")
    hyp.append("taux_collecte_prevu")

    # prélèvements : la base dit si du tissu avant traitement est collecté, pas dans quels bras
    prelevements = None
    if samples.get("pre_treatment_tissue"):
        prelevements = [{"materiel": "tissu_tumoral_fixe", "instant_j": FENETRE_TISSU_J,
                         "bras": [b["nom"] for b in bras], "statut": "prevu"}]
        hyp.append("prelevements.bras (supposé : tous les bras)")
        cit = next((i.get("quote") for i in samples.get("items") or [] if "tissue" in str(i.get("material")).lower()
                    or "tumor" in str(i.get("material")).lower()), None)
        src["prelevements"] = {"doc": tid, "passage": cit}

    codes = (j.get("outcomes", {}).get("primary_codes") or []) + (j.get("outcomes", {}).get("codes") or [])
    criteres = []
    for c in codes:
        for rx, k in CRITERES:
            if rx.search(str(c)) and k not in criteres:
                criteres.append(k)

    if samples.get("consent_quote"):
        src["consentement_portee"] = {"doc": tid, "passage": samples["consent_quote"]}
    for h in hyp:
        src[h] = {"doc": "valeur par défaut TrialRevive", "passage": "hypothèse à valider"}

    return {
        "trial_id": tid, "nct_id": ident.get("nct_id"),
        "index": "interne" if str(tid).startswith("RFE-") else "externe",
        "titre": ident.get("title"), "detenteur": samples.get("holder") or ident.get("sponsor"),
        "corpus": (j.get("provenance") or {}).get("corpus"),
        "date_debut": dates.get("start") or dates.get("first_posted") or "9999-12-31",
        "indication": " ; ".join((ind.get("labels") or []) + (ind.get("conditions") or [])),
        "domaine": ind.get("domain"), "stade": stade, "ligne": ind.get("line"),
        "randomise": bool(design.get("randomized")),
        "traitement": {"molecules": mols, "classes": cl_exp, "classe": cl_exp[0] if len(cl_exp) == 1 else None},
        "comparateur": {"description": ", ".join(contrast.get("control_arms") or []) or None,
                        "classes": cl_ctrl, "type_contraste": contrast.get("type")},
        "effectif_randomise": effectif,
        "bras": bras or None,
        "criteres": criteres,
        "prelevements": prelevements,
        "taux_collecte_prevu": COUVERTURE_DEFAUT,
        "taux_evenements_prevu": taux_evt,
        "consentement_portee": CONSENT.get(samples.get("consent"), "inconnu"),
        "biomarqueurs_mesures": [b.get("gene") or b.get("label") for b in j.get("biomarkers") or []
                                 if "measured" in (b.get("statuses") or []) or "measured" in (b.get("roles") or [])],
        "statut_a_la_coupure": dates.get("status_at_cutoff"),
        "hypotheses": hyp,
        "sources": src,
        "confiance": {"valeurs_par_defaut": 0.3},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entree")
    ap.add_argument("--corpus", help="ne garder que les lignes dont le corpus contient ce texte")
    ap.add_argument("--sortie", default="data/fiches_base.json")
    a = ap.parse_args()
    fiches, vus = [], set()
    for j in lire(a.entree):
        if j.get("record_type") not in (None, "trial"):
            continue
        f = vers_fiche(j)
        if a.corpus and a.corpus.lower() not in str(f["corpus"]).lower():
            continue
        if (f["trial_id"], f["corpus"] if not a.corpus else None) in vus:
            continue
        vus.add((f["trial_id"], f["corpus"] if not a.corpus else None))
        fiches.append(f)
    json.dump(fiches, open(a.sortie, "w"), ensure_ascii=False, indent=1)
    n_eff = sum(f["effectif_randomise"] is not None for f in fiches)
    n_tissu = sum(f["prelevements"] is not None for f in fiches)
    n_bras = sum(f["bras"] is not None for f in fiches)
    print(f"{len(fiches)} fiches écrites dans {a.sortie}")
    print(f"  avec effectif : {n_eff} · avec bras décrits : {n_bras} · avec tissu avant traitement : {n_tissu}")


if __name__ == "__main__":
    main()
