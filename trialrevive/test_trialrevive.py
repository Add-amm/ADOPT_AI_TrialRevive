"""Tests : python -m pytest -q"""
import json

import pytest

import fetch_ctgov
import matcher
import stats

# --- chiffres de l'exemple de la description technique (section 6)
def test_exigence_exemple_section6():
    assert round(stats.evenements_requis_interaction(0.45, 1.0, 0.45)) == 199


@pytest.mark.parametrize("d, attendu", [(120, 0.58), (230, 0.85)])
def test_puissance_exemple_section6(d, attendu):
    pw = stats.puissance_interaction(0.45 * d, 0.55 * d, 0.45, 1.0)
    assert pw == pytest.approx(attendu, abs=0.01)


def test_schoenfeld_exemple_5_7_4():
    t = stats.taille_essai_confirmation(0.55, 1.0, 0.5)
    assert t["hr_dilue_tous"] == pytest.approx(0.74, abs=0.01)
    assert 340 <= t["evenements_essai_tous"] <= 360
    assert 85 <= t["evenements_essai_x_plus"] <= 92


def test_masquage_suppression_secondaire():
    cascade = {"A": [210, 186, 170, 151, 147], "B": [210, 185, 170, 151, 141]}
    m = stats.masquer_cascade(cascade)
    # 151 -> 147 : écart de 4 < 5, donc S4 masqué dans les deux bras
    assert m["A"][4] == "<5" and m["B"][4] == "<5"
    assert m["A"][0] == 210


def test_score_temporel():
    assert matcher.score_temporel([-28, -1], [-20, -5], 62) == 1.0
    assert matcher.score_temporel([-28, -1], [-59, -29], 62) == pytest.approx(1 - 1 / 62)
    assert matcher.score_temporel([-28, -1], [-200, -100], 62) is None


# --- moteur sur les fiches fictives
@pytest.fixture(scope="module")
def res():
    seh = json.load(open("data/seh_kras_2009.json"))
    fiches = json.load(open("data/fiches_essais_fictives.json"))
    return matcher.apparier(seh, fiches)


def test_internes_et_externes_separes(res):
    assert all(r["index"] == "interne" for r in res["internes"])
    assert all(r["index"] == "externe" for r in res["externes"])


def test_bon_essai_en_tete(res):
    assert res["internes"][0]["trial_id"] == "FICTIF-INT-01"


def test_raisons_exclusion(res):
    raisons = {x["trial_id"]: " ".join(x["raisons"]) for x in res["exclus"]}
    assert "tiré au sort" in raisons["FICTIF-EXT-03"]
    assert "pas avant la date" in raisons["FICTIF-EXT-04"]
    assert "pas dans" in raisons["FICTIF-EXT-05"]
    assert "puissance" in raisons["FICTIF-EXT-06"]
    assert "anti-EGFR" in raisons["FICTIF-EXT-08"]


def test_tolerance_plafonne_preuve(res):
    ext = {r["trial_id"]: r for r in res["externes"]}
    assert ext["FICTIF-EXT-02"]["niveau_preuve_atteignable"] == "E2"  # couverture 69 %
    assert ext["FICTIF-EXT-07"]["niveau_preuve_atteignable"] == "E2"  # critère substitué
    assert all(g["code"] not in ("G3", "G4", "G6") for g in ext["FICTIF-EXT-02"]["gains"])


def test_fiche_registre_incomplete_va_a_completer():
    seh = json.load(open("data/seh_kras_2009.json"))
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT_TEST", "briefTitle": "Test"},
        "statusModule": {"startDateStruct": {"date": "2005-03"}},
        "conditionsModule": {"conditions": ["Metastatic Colorectal Cancer"]},
        "designModule": {"designInfo": {"allocation": "RANDOMIZED"}, "enrollmentInfo": {"count": 400}},
        "armsInterventionsModule": {"armGroups": [
            {"label": "Pmab + BSC", "type": "EXPERIMENTAL", "interventionNames": ["Drug: panitumumab"]},
            {"label": "BSC", "type": "ACTIVE_COMPARATOR", "interventionNames": ["Other: best supportive care"]}]},
        "outcomesModule": {"primaryOutcomes": [{"measure": "Progression-free survival"}]}}}
    fiche = fetch_ctgov.vers_fiche(study)
    assert fiche["date_debut"] == "2005-03-01" and fiche["criteres"] == ["PFS"]
    r = matcher.apparier(seh, [fiche])
    assert r["a_completer"] and r["a_completer"][0]["trial_id"] == "NCT_TEST"


def _etude(nct, arms, interventions=None, conditions=("Metastatic Colorectal Cancer",), titre="Test"):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": titre},
        "statusModule": {"startDateStruct": {"date": "2005-03"}},
        "conditionsModule": {"conditions": list(conditions)},
        "designModule": {"designInfo": {"allocation": "RANDOMIZED"}, "enrollmentInfo": {"count": 700}},
        "armsInterventionsModule": {"armGroups": arms,
                                    "interventions": [{"name": n} for n in (interventions or [])]},
        "outcomesModule": {"primaryOutcomes": [{"measure": "Progression-free survival"}]}}}


@pytest.fixture(scope="module")
def seh():
    return json.load(open("data/seh_kras_2009.json"))


def test_anti_egfr_ajoute_a_bevacizumab_reste_candidat(seh):
    # type CAIRO2 / PACCE : chimio + bevacizumab +/- anti-EGFR
    f = fetch_ctgov.vers_fiche(_etude("T1", [
        {"label": "A", "type": "ACTIVE_COMPARATOR", "interventionNames": ["Drug: capecitabine", "Drug: bevacizumab"]},
        {"label": "B", "type": "EXPERIMENTAL", "interventionNames": ["Drug: capecitabine", "Drug: bevacizumab", "Drug: cetuximab"]}]))
    assert matcher.etage1(seh, f) == []


def test_enregistrement_ancien_sans_bras_va_a_completer(seh):
    # type CO.17 / COIN : aucun bras décrit dans le registre
    f = fetch_ctgov.vers_fiche(_etude("T2", [], interventions=["Drug: cetuximab", "Other: best supportive care"]))
    assert matcher.etage1(seh, f) == []
    assert matcher.apparier(seh, [f])["a_completer"]


def test_tous_les_bras_avec_anti_egfr_exclu(seh):
    # type étude de toxicité cutanée : panitumumab dans tous les bras
    f = fetch_ctgov.vers_fiche(_etude("T3", [
        {"label": "A", "type": "EXPERIMENTAL", "interventionNames": ["Drug: panitumumab", "Drug: doxycycline"]},
        {"label": "B", "type": "EXPERIMENTAL", "interventionNames": ["Drug: panitumumab"]}]))
    assert any("tous les bras" in r for r in matcher.etage1(seh, f))


def test_adjuvant_stade_iii_exclu(seh):
    f = fetch_ctgov.vers_fiche(_etude("T4", [
        {"label": "A", "type": "EXPERIMENTAL", "interventionNames": ["Drug: cetuximab", "Drug: FOLFOX"]},
        {"label": "B", "type": "ACTIVE_COMPARATOR", "interventionNames": ["Drug: FOLFOX"]}],
        conditions=["Stage III Colon Cancer"], titre="Adjuvant FOLFOX with or without cetuximab"))
    assert any("non métastatique" in r for r in matcher.etage1(seh, f))


def test_colon_et_rectum_dans_le_champ(seh):
    f = fetch_ctgov.vers_fiche(_etude("T5", [
        {"label": "A", "type": "EXPERIMENTAL", "interventionNames": ["Drug: panitumumab"]},
        {"label": "B", "type": "ACTIVE_COMPARATOR", "interventionNames": ["Other: BSC"]}],
        conditions=["Stage IV Colon Cancer", "Stage IV Rectal Cancer"]))
    assert matcher.etage1(seh, f) == []
