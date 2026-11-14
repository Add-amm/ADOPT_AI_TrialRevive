"""Adaptation de présentation : vrai Backend/matcher.py, fiches fictives uniquement."""
import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from frontend_matcher import BACKEND, BackendFrontendService, BackendUnavailable


@pytest.fixture
def rich_fiches(tmp_path):
    fiches = json.loads((BACKEND / "data/fiches_essais_fictives.json").read_text())
    pending = copy.deepcopy(fiches[0])
    pending.update(trial_id="FICTIF-A-COMPLETER", titre="Fiche fictive incomplète", effectif_randomise=None)
    ongoing = copy.deepcopy(fiches[0])
    ongoing.update(trial_id="FICTIF-EN-COURS", titre="Essai fictif en cours", date_debut="2010-06-01", first_posted="2008-01-01")
    ranged = copy.deepcopy(fiches[0])
    ranged.update(trial_id="FICTIF-FOURCHETTE", titre="Essai fictif en fourchette", effectif_randomise=1100,
                  taux_collecte_prevu=[0.6, 0.9])
    path = tmp_path / "fiches-fictives.json"
    path.write_text(json.dumps(fiches + [pending, ongoing, ranged]))
    return path


def test_all_five_backend_groups_are_kept_and_no_global_verdict_is_invented(rich_fiches):
    service = BackendFrontendService(fiches=rich_fiches)
    response = service.analyze(service.info()["exemple"])
    raw, d = response["resultat_backend"], response["dossier"]
    for key in ("internes", "externes", "a_completer", "en_cours"):
        assert [r["trial_id"] for r in d[key]] == [r["trial_id"] for r in raw[key]]
    assert len(d["ecartes"]) == len(raw["exclus"])
    assert sum(len(d[k]) for k in ("internes", "externes", "ecartes", "a_completer", "en_cours")) == raw["n_essais_examines"] == 11
    assert len(d["a_completer"]) == len(d["en_cours"]) == 1
    assert d["a_completer"][0]["retenu"] is None and d["en_cours"][0]["retenu"] is None
    assert d["statistique"]["suffisant"] is None and d["verdict"]["preuve_verifiee"] is None
    assert d["verdict"]["E"] is None and d["verdict"]["R"] is None and d["verdict"]["G"] == []
    assert d["utilisables"] is None and d["gain"]["gain_sauvage_mois"] is None
    ranged = next(r for r in d["retenus"] if r["trial_id"] == "FICTIF-FOURCHETTE")
    assert ranged["couverture"] == [0.6, 0.9]
    assert ranged["puissance_a_priori"] is not None
    assert "FICTIF-A-COMPLETER" in response["markdown"] and "FICTIF-EN-COURS" in response["markdown"]


def test_duplicate_metadata_follows_the_backend_complete_fiche_selection(tmp_path):
    complete = json.loads((BACKEND / "data/fiches_essais_fictives.json").read_text())[0]
    complete.update(trial_id="FICTIF-DOUBLON", nct_id="NCT00000001")
    incomplete = copy.deepcopy(complete)
    incomplete.update(nct_id=None, effectif_randomise=None)
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps([incomplete, complete]))
    service = BackendFrontendService(fiches=path)
    data = service.analyze(service.info()["exemple"])
    assert data["resultat_backend"]["n_lignes_recues"] == 2
    assert data["resultat_backend"]["n_essais_examines"] == 1
    assert data["dossier"]["internes"][0]["nct_id"] == "NCT00000001"


def test_postgres_is_default_and_failure_cannot_fall_back_to_old_data(monkeypatch):
    calls = []
    def no_connection(command, **kwargs):
        calls.append((command, kwargs))
        target = Path(command[command.index("--sortie") + 1])
        target.write_text(json.dumps({"error": "Connexion du backend indisponible. Configuration manquante."}))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(subprocess, "run", no_connection)
    service = BackendFrontendService()
    assert service.info()["source"] == "postgres"
    with pytest.raises(BackendUnavailable, match="Configuration manquante"):
        service.analyze(service.info()["exemple"])
    assert len(calls) == 1 and "--fiches" not in calls[0][0]
    assert calls[0][1]["cwd"] == BACKEND


def test_free_question_is_rejected_before_database_access(monkeypatch):
    def not_called(*args, **kwargs):
        pytest.fail("Une question non prise en charge ne doit pas appeler le backend")
    monkeypatch.setattr(subprocess, "run", not_called)
    with pytest.raises(ValueError, match="SEH structurée"):
        BackendFrontendService().analyze("Une question scientifique différente")


def test_hypothesis_id_calls_the_same_backend_hypothesis():
    service = BackendFrontendService(fiches=BACKEND / "data/fiches_essais_fictives.json")
    question = service.info()["exemple"]
    assert service.analyze("SEH-KRAS-2009")["dossier"]["question"] == question


def test_worker_timeout_has_a_public_diagnostic(monkeypatch):
    def timed_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1, stderr="private-fixture-detail")
    monkeypatch.setattr(subprocess, "run", timed_out)
    service = BackendFrontendService(timeout=1)
    with pytest.raises(BackendUnavailable) as err:
        service.analyze(service.info()["exemple"])
    assert "délai" in str(err.value) and "private-fixture-detail" not in str(err.value)


def test_invalid_worker_output_does_not_expose_raw_logs(monkeypatch):
    def unavailable(command, **kwargs):
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(subprocess, "run", unavailable)
    service = BackendFrontendService()
    with pytest.raises(BackendUnavailable, match="résultat lisible"):
        service.analyze(service.info()["exemple"])
