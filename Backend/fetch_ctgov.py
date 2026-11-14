"""Récupère des essais publics sur ClinicalTrials.gov (API v2) et produit des fiches.

À lancer sur un ordinateur avec accès internet :
    python fetch_ctgov.py --cond "colorectal cancer" --intr "cetuximab OR panitumumab" \
        --avant 2009-01-01 --sortie data/fiches_ctgov.json

Le registre ne donne pas les prélèvements, la couverture, le taux d'événements ni le
consentement : ces champs restent à null et le moteur classe l'essai « à compléter ».
On les remplit ensuite à la main ou par lecture IA (avec source et passage).
"""
import argparse
import json
import re
import urllib.parse
import urllib.request

API = "https://clinicaltrials.gov/api/v2/studies"
CLASSES = {"cetuximab": "anti-EGFR", "panitumumab": "anti-EGFR",
           "bevacizumab": "anti-VEGF", "aflibercept": "anti-VEGF"}
CIBLES_CONNUES = {"cetuximab": "EGFR", "panitumumab": "EGFR", "gefitinib": "EGFR",
                  "erlotinib": "EGFR", "bevacizumab": "VEGF", "aflibercept": "VEGF"}
CHIMIO = re.compile(r"folf|oxaliplatin|irinotecan|fluorouracil|5-fu|capecitabin|leucovorin|xelox|capox", re.I)
CRITERES = [(re.compile(r"progression[- ]free|\bPFS\b", re.I), "PFS"),
            (re.compile(r"overall survival|\bOS\b", re.I), "OS"),
            (re.compile(r"response rate|objective response|\bORR\b", re.I), "ORR")]


def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def classes_de(noms):
    out = set()
    for n in noms:
        for mol, cl in CLASSES.items():
            if mol in n.lower():
                out.add(cl)
        if CHIMIO.search(n):
            out.add("chimiotherapie")
    return sorted(out)


STADE_META = re.compile(r"metasta|stage iv|advanced|unresectable|recurrent", re.I)
STADE_LOCAL = re.compile(r"stage (ii|iii)\b|adjuvant|resect|removed by surgery|before and after surgery|"
                         r"neoadjuvant|radiation therapy|chemoradi", re.I)


def molecules_de(noms):
    return sorted({m for m in CLASSES for n in noms if m in n.lower()})


def stade_de(texte):
    """Heuristique : 'metastatique', 'local' ou None (inconnu, non éliminatoire)."""
    meta, local = bool(STADE_META.search(texte)), bool(STADE_LOCAL.search(texte))
    if meta and not local:
        return "metastatique"
    if local and not meta:
        return "local"
    return None  # ambigu ou absent : à vérifier à la main


def vers_fiche(study):
    p = study["protocolSection"]
    ident, statut, design = p["identificationModule"], p.get("statusModule", {}), p.get("designModule", {})
    arms = p.get("armsInterventionsModule", {})
    nct = ident["nctId"]
    interventions = [i.get("name", "") for i in arms.get("interventions", [])]

    # bras : les anciens enregistrements n'en décrivent souvent aucun -> null (à compléter)
    bras = []
    for b in arms.get("armGroups", []):
        noms = b.get("interventionNames", [])
        bras.append({"nom": b.get("label"), "type": b.get("type"), "n": None,
                     "interventions": noms, "classes": classes_de(noms)})
    exp = [b for b in bras if b["type"] == "EXPERIMENTAL"]
    ctrl = [b for b in bras if b["type"] != "EXPERIMENTAL"]

    # molécules étudiées : bras expérimentaux, sinon toutes les interventions
    mols = molecules_de([n for b in exp for n in b["interventions"]] or interventions)
    classes_exp = sorted({CLASSES[m] for m in mols})

    conditions = " ; ".join(p.get("conditionsModule", {}).get("conditions", []))
    texte_stade = " ".join([conditions, ident.get("briefTitle", ""), ident.get("officialTitle", "")])
    primaires = " ".join(o.get("measure", "") for o in p.get("outcomesModule", {}).get("primaryOutcomes", []))
    secondaires = " ".join(o.get("measure", "") for o in p.get("outcomesModule", {}).get("secondaryOutcomes", []))
    criteres = [k for rx, k in CRITERES if rx.search(primaires)] or \
               [k for rx, k in CRITERES if rx.search(secondaires)]
    src = lambda champ: {"doc": f"ClinicalTrials.gov {nct}", "passage": champ}
    return {
        "trial_id": nct, "index": "externe", "titre": ident.get("briefTitle"),
        "detenteur": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
        "date_debut": _date(statut),
        "first_posted": statut.get("studyFirstPostDateStruct", {}).get("date"),
        "indication": conditions,
        "stade": stade_de(texte_stade),
        "randomise": design.get("designInfo", {}).get("allocation") == "RANDOMIZED",
        "cibles": sorted({CIBLES_CONNUES[m] for m in mols if m in CIBLES_CONNUES}),
        "traitement": {"molecules": mols, "classes": classes_exp,
                       "classe": classes_exp[0] if len(classes_exp) == 1 else None},
        "comparateur": {"description": "; ".join(n for b in ctrl for n in b["interventions"]) or None,
                        "classes": sorted({c for b in ctrl for c in b["classes"]})},
        "effectif_randomise": design.get("enrollmentInfo", {}).get("count"),
        "bras": bras or None,
        "criteres": criteres,
        "prelevements": None, "taux_collecte_prevu": None,
        "taux_evenements_prevu": None, "consentement_portee": None,
        "biomarqueurs_mesures": [],
        "phases": design.get("phases", []),
        "biospecimen_registre": design.get("bioSpec"),
        "sources": {"design": src("designModule"), "bras": src("armsInterventionsModule"),
                    "criteres": src("outcomesModule"), "date_debut": src("statusModule.startDateStruct"),
                    "stade": src("conditionsModule + titre (heuristique, à vérifier)")},
        "confiance": {"registre": 0.9, "stade": 0.6, "champs_a_completer": 0.0},
    }


def _date(statut):
    d = statut.get("startDateStruct", {}).get("date") or "9999-12"
    return d if len(d) == 10 else d + "-01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", default="colorectal cancer")
    ap.add_argument("--intr", default="cetuximab OR panitumumab")
    ap.add_argument("--avant", default="2009-01-01")
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--sortie", default="data/fiches_ctgov.json")
    ap.add_argument("--depuis-brut", dest="depuis_brut", default=None,
                    help="refaire les fiches depuis data/ctgov_brut.json, sans internet")
    a = ap.parse_args()
    params = {"query.cond": a.cond, "query.intr": a.intr, "pageSize": 100, "format": "json",
              "filter.advanced": f"AREA[StartDate]RANGE[MIN,{a.avant}]"}
    brut, token = [], None
    if a.depuis_brut:
        brut = json.load(open(a.depuis_brut))
    else:
        while len(brut) < a.max:
            if token:
                params["pageToken"] = token
            data = get(params)
            brut += data.get("studies", [])
            token = data.get("nextPageToken")
            if not token:
                break
        json.dump(brut, open("data/ctgov_brut.json", "w"), ensure_ascii=False)
    fiches = [vers_fiche(s) for s in brut]
    json.dump(fiches[: a.max], open(a.sortie, "w"), ensure_ascii=False, indent=2)
    print(f"{len(fiches[: a.max])} fiches écrites dans {a.sortie}")


if __name__ == "__main__":
    main()
