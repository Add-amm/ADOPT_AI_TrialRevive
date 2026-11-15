"""Tests de l'adaptateur trialstd : python -m pytest -q

Toutes les données ci-dessous sont fabriquées (molécule « fictimab », essais FAKE-…), au format trialstd 1.0.
"""
import copy

import matcher
import trialstd_adapter as A

HYP = {
    "id": "hyp_fictive", "cutoff_date": "2010-01-01", "setting": "advanced",
    "free_text": "Le statut du marqueur X modifie-t-il le bénéfice du fictimab dans le cancer fictif métastatique ?",
    "normalized": {
        "drugs": [{"kind": "drug", "id": "CHEMBL000001", "name": "fictimab", "source": "text",
                   "classes": [{"id": "cls:anti-fict-antibody", "label": "anti-FICT antibody"}]}],
        "drug_classes": [{"id": "cls:anti-fict-antibody", "label": "anti-FICT antibody", "source": "curated"}],
        "targets": [{"symbol": "FICT"}],
        "indication": {"labels": ["fictional cancer"], "diseases": [{"id": "MONDO_0000001"}], "setting": "advanced"},
        "comparator": {"type": "without_class"},
        "outcomes": {"codes": ["PFS", "OS"]},
        "material": {"kind": "tissue_ffpe", "moment": "pre"},
        "expected_prevalence": {"value": 0.4},
        "biomarkers": [{"key": "gene:X", "label": "X mutation", "id": "HGNC:0"}],
    },
}


def essai(tid, **diff):
    """Essai randomisé idéal : fictimab ajouté à une chimiothérapie, tissu avant traitement dans les deux bras."""
    t = {
        "id": tid, "identity": {"title": f"Chemotherapy with or without fictimab ({tid})", "sponsor": "Fictive"},
        "indication": {"conditions": ["Fictional Cancer"], "labels": ["fictional cancer"],
                       "diseases": [{"id": "MONDO_0000001", "name": "fictional cancer", "ancestors": []}],
                       "setting": "advanced"},
        "design": {"randomized": True, "enrollment": 800, "phases": ["PHASE3"],
                   "arms": [{"label": "Chemo + fictimab", "role": "experimental", "drugs": ["fictimab", "chemo"]},
                            {"label": "Chemo", "role": "active_comparator", "drugs": ["chemo"]}],
                   "contrast": {"type": "add_on", "differential_drugs": ["fictimab"], "background_drugs": ["chemo"]}},
        "interventions": [{"kind": "drug", "id": "CHEMBL000001", "name": "fictimab",
                           "classes": [{"id": "cls:anti-fict-antibody", "label": "anti-FICT antibody"}]},
                          {"kind": "drug", "id": "text:chemo", "name": "chemo", "classes": []}],
        "samples": {"items": [{"material": "tissue_ffpe", "moment": "pre", "mandatory": True, "purpose": "biomarker",
                               "field": "eligibility", "quote": "archival tumour tissue required"}],
                    "consent": "broad", "events_primary_analysis": 600},
        "dates": {"start": "2005-01", "status_at_cutoff": "completed"},
        "outcomes": {"primary_codes": ["PFS"], "codes": ["PFS", "OS"]},
        "biomarkers": [],
    }
    for k, v in diff.items():
        t[k] = v
    return t


def classer(essais):
    items, detail = A.classement(copy.deepcopy(HYP), essais)
    return items, detail


def test_import_ne_modifie_pas_le_moteur():
    assert "effectif_randomise" not in matcher.CHAMPS_ETAGE2
    classer([essai("FAKE-1")])
    assert "effectif_randomise" not in matcher.CHAMPS_ETAGE2 and "criteres" not in matcher.CHAMPS_ETAGE2


def test_ordre_des_verdicts():
    ideal = essai("FAKE-1")
    bras_unique = essai("FAKE-2", design={**ideal["design"], "randomized": False, "arms": ideal["design"]["arms"][:1]})
    autre_maladie = essai("FAKE-3", indication={"conditions": ["Other Disease"], "labels": ["other disease"],
                                                "diseases": [{"id": "MONDO_0000002"}], "setting": "advanced"})
    en_cours = essai("FAKE-4", design={**ideal["design"], "enrollment": None},
                     dates={"start": "2009-06", "status_at_cutoff": "ongoing"})
    items, detail = classer([autre_maladie, bras_unique, en_cours, ideal])
    ordre = [x["nct_id"] for x in items]
    assert ordre[0] == "FAKE-1" and items[0]["verdict"] == "retained"
    assert ordre[1] == "FAKE-4" and items[1]["verdict"] == "ongoing"
    assert {x["verdict"] for x in items[2:]} == {"excluded"}
    scores = [x["score"] for x in items]
    assert scores == sorted(scores, reverse=True)
    assert detail["resultat_moteur"]["a_completer"][0]["champs_manquants"] == ["effectif_randomise"]


def test_bras_placebo_ne_recoit_pas_la_molecule():
    # « fictimab/placebo » attribué aux deux bras : le bras placebo reste un contrôle sans la classe
    design = {"randomized": True, "enrollment": 800, "phases": ["PHASE3"],
              "arms": [{"label": "Fictimab", "role": "experimental", "drugs": ["fictimab"]},
                       {"label": "Placebo", "role": "placebo_comparator", "drugs": ["fictimab"],
                        "controls": ["placebo"]}],
              "contrast": {"type": "placebo", "differential_drugs": ["fictimab"], "background_drugs": []}}
    items, _ = classer([essai("FAKE-5", design=design)])
    assert items[0]["verdict"] == "retained"


def test_forme_de_sel_reconnue():
    interventions = [{"kind": "drug", "id": "CHEMBL999999", "name": "fictimab sodium", "classes": []},
                     {"kind": "drug", "id": "text:chemo", "name": "chemo", "classes": []}]
    design = copy.deepcopy(essai("x")["design"])
    design["arms"][0]["drugs"] = ["fictimab sodium", "chemo"]
    items, _ = classer([essai("FAKE-6", interventions=interventions, design=design)])
    assert items[0]["verdict"] == "retained"


def test_sans_prelevement_a_completer():
    items, detail = classer([essai("FAKE-7", samples={"items": [], "consent": None})])
    assert items[0]["verdict"] == "borderline"
    assert "prelevements" in detail["resultat_moteur"]["a_completer"][0]["champs_manquants"]


def test_point_entree_banc():
    corpus = [{"trialrevive": {"id": "FAKE-1"}, "standardized": essai("FAKE-1"),
               "protocolSection": {"identificationModule": {"briefTitle": "Chemotherapy with or without fictimab (FAKE-1)"},
                                   "eligibilityModule": {"eligibilityCriteria": "archival tumour tissue required"}}},
              {"trialrevive": {"id": "FAKE-8"}, "protocolSection": {}}]
    items = A.classer_pour_banc({"standardized": copy.deepcopy(HYP)}, corpus)
    assert [x["nct_id"] for x in items] == ["FAKE-1", "FAKE-8"]
    assert items[1]["verdict"] == "excluded" and items[1]["score"] == 0.0
    citations = {e["quote"] for e in items[0]["evidence"]}
    assert "archival tumour tissue required" in citations
