"""Tests des nouvelles routes sur un vrai serveur et le backend local inchangé."""
import contextlib
import json
import socket
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import requests
import uvicorn

import server
from src import compare
from frontend_matcher import BackendFrontendService, BACKEND
from web_adapter import adapt_dossier, json_value

DEMO = BackendFrontendService(fiches=BACKEND / "data/fiches_essais_fictives.json")
EXAMPLE = DEMO.info()["exemple"]


@contextlib.contextmanager
def running_app(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if srv.started:
                break
            if not thread.is_alive():
                pytest.fail("Le serveur de test s'est arrêté au démarrage")
            time.sleep(0.02)
        else:
            pytest.fail("Le serveur de test n'est pas prêt")
        yield base
    finally:
        srv.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture(scope="module")
def web_api(tmp_path_factory):
    directory = tmp_path_factory.mktemp("web-baselines")
    with running_app(server.create_app(baseline_dir=directory, service=DEMO)) as base:
        yield base, directory


@pytest.fixture
def record():
    return {"question": EXAMPLE,
            "modele": "Fixture de test uniquement", "date": "2026-11-14",
            "reponse_ia": "  NCT00364013 et NCT99999999.\n<script>window.injected=true</script>\n"}


def test_routes_use_the_existing_backend_without_recalculating_results(web_api, tmp_path):
    import subprocess
    import sys

    base, _ = web_api
    output = tmp_path / "raw-backend.json"
    subprocess.run([sys.executable, str(BACKEND / "matcher.py"),
                    str(BACKEND / "data/seh_kras_2009.json"),
                    str(BACKEND / "data/fiches_essais_fictives.json"), str(output)],
                   cwd=BACKEND, capture_output=True, check=True)
    raw = json.loads(output.read_text())
    response = requests.post(base + "/api/analyze", json={"question": EXAMPLE}, timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert data["resultat_backend"] == raw
    d = data["dossier"]
    assert d["backend"] == "Backend/matcher.py"
    assert d["rejection"]["total"] == 8 and len(d["internes"]) == 1 and len(d["externes"]) == 2
    assert len(d["ecartes"]) == 5
    assert d["utilisables"] is None and d["entonnoir"] == [] and d["groupes"] == []
    assert d["verdict"]["E"] is None and d["verdict"]["R"] is None and d["verdict"]["G"] == []
    assert d["statistique"]["evenements_necessaires_total"] == raw["exigence_statistique"]["evenements_min"]
    assert d["statistique"]["evenements_necessaires_par_groupe"] is None
    assert [r["trial_id"] for r in d["internes"]] == [r["trial_id"] for r in raw["internes"]]
    assert [r["trial_id"] for r in d["externes"]] == [r["trial_id"] for r in raw["externes"]]
    for source, target in zip(raw["internes"] + raw["externes"], d["retenus"]):
        assert target["score"] == source["score_compatibilite"]
        assert target["E"] == source["niveau_preuve_atteignable"]
        assert target["conditions"] == source["conditions_restantes"]
        assert target["gains"] == source["gains"]
        assert target["references"] == source["sources"]
    assert all(s["lien"] is None for s in d["sources"])  # identifiants fictifs, aucun NCT inventé
    assert "206 événements nécessaires au total" in data["markdown"]
    assert "252" not in data["markdown"]


def test_adapter_never_fabricates_numbers_sources_or_validation():
    source = {"question": "Question", "retenus": [{"nct_id": "NCT00364013"}]}
    adapted = adapt_dossier(source)
    assert source == {"question": "Question", "retenus": [{"nct_id": "NCT00364013"}]}
    assert adapted["utilisables"] is None and adapted["sources"] == [] and adapted["entonnoir"] == []
    assert adapted["verdict"]["preuve_verifiee"] is None
    assert adapted["verdict"]["E"] == "non calculé"
    assert adapted["retenus"][0]["nb_patients"] is None
    assert adapted["retenus"][0]["lien"] is None
    assert adapted["statistique"]["suffisant"] is None


def test_strict_json_converts_numpy_and_missing_floats():
    value = {"n": np.int64(7), "score": np.float64(0.7), "ok": np.bool_(False),
             "unknown": [float("nan"), float("inf"), np.float64("-inf")]}
    converted = json_value(value)
    assert json.loads(json.dumps(converted, allow_nan=False)) == {"n": 7, "score": 0.7, "ok": False,
                                                                 "unknown": [None, None, None]}
    with pytest.raises(TypeError):
        json_value(object())


def test_info_and_download_match_the_same_analysis(web_api):
    base, _ = web_api
    info = requests.get(base + "/api/info", timeout=5).json()
    assert info["exemple"] == EXAMPLE and info["backend"] == "Backend/matcher.py"
    assert info["source"] == "fichier" and info["donnees_fictives"] is True
    r = requests.get(base + "/api/dossier.md", params={"question": EXAMPLE}, timeout=5)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text == DEMO.analyze(EXAMPLE)["markdown"]


@pytest.mark.parametrize("payload", [None, [], "texte", {}, {"question": ""}, {"question": 123},
    {"question": {}}, {"question": "x" * 601}, {"question": "Météo ?"},
    {"question": "Le statut NRAS change-t-il l'effet du panitumumab ?"}])
def test_invalid_analysis_is_a_json_error(web_api, payload):
    base, _ = web_api
    r = requests.post(base + "/api/analyze", data=json.dumps(payload), timeout=5)
    assert r.status_code == 400 and isinstance(r.json()["error"], str)


def test_malformed_and_oversized_requests_are_rejected(web_api):
    base, _ = web_api
    for data in ("{", b"\xff", ""):
        r = requests.post(base + "/api/analyze", data=data, timeout=5)
        assert r.status_code == 400 and "error" in r.json()
    r = requests.post(base + "/api/analyze", data="x" * (server.MAX_BODY + 1), timeout=5)
    assert r.status_code == 413 and "volumineuse" in r.json()["error"]


def test_free_question_does_not_silently_replace_the_structured_hypothesis(web_api):
    base, _ = web_api
    r = requests.post(base + "/api/analyze", json={"question": "Le statut KRAS change-t-il l'effet du cetuximab ?"}, timeout=5)
    assert r.status_code == 400 and "SEH structurée" in r.json()["error"]


def test_validate_archive_list_compare_are_lossless_and_isolated(web_api, record):
    base, directory = web_api
    r = requests.post(base + "/api/baselines/validate", json={"text": json.dumps(record)}, timeout=5)
    assert r.status_code == 200 and r.json()["record"] == record
    # Aucun nom ou chemin de sortie n'est accepté du client.
    body = {"record": record, "filename": "../../evil.json"}
    first = requests.post(base + "/api/baselines/archive", json=body, timeout=5)
    again = requests.post(base + "/api/baselines/archive", json=body, timeout=5)
    assert first.status_code == again.status_code == 200 and first.json() == again.json()
    assert (directory / first.json()["archive"]).parent == directory
    records = requests.get(base + "/api/baselines", timeout=5).json()
    assert record in records["records"] and records["errors"] == []
    out = requests.post(base + "/api/compare", json={"question": record["question"], "record": record}, timeout=5)
    assert out.status_code == 200
    d = out.json()
    assert d["meme_question"] is True and d["rows"][0]["IA généraliste (évaluation déclarée)"] == "Non évalué"
    ncts = {row["NCT cité"]: row["Cache local"] for row in d["nct"]}
    assert ncts["NCT00364013"].startswith("Absent") and ncts["NCT99999999"].startswith("Absent")
    other = {**record, "question": "Question différente"}
    out = requests.post(base + "/api/compare", json={"question": record["question"], "record": other}, timeout=5).json()
    assert out["meme_question"] is False
    assert all(row["TrialRevive"] == "Non évalué sur cette question" for row in out["rows"])
    assert len(list(directory.glob("*.json"))) == 1


@pytest.mark.parametrize("route,payload", [
    ("/api/baselines/validate", {"text": "[]"}), ("/api/baselines/validate", {"text": {}}),
    ("/api/baselines/archive", {"record": {}}), ("/api/compare", {"record": []}),
])
def test_baseline_errors_keep_the_json_error_shape(web_api, route, payload):
    base, _ = web_api
    r = requests.post(base + route, json=payload, timeout=5)
    assert r.status_code == 400 and "error" in r.json()


@pytest.mark.parametrize("route", ["/api/baselines/validate", "/api/baselines/archive", "/api/compare"])
def test_optional_context_must_be_text_per_contract(web_api, record, route):
    base, _ = web_api
    invalid = {**record, "contexte": {"not": "text"}}
    body = {"text": json.dumps(invalid)} if route.endswith("validate") else {"record": invalid}
    r = requests.post(base + route, json=body, timeout=5)
    assert r.status_code == 400 and "contexte" in r.json()["error"]


def test_existing_bad_archive_is_reported_without_touching_it(tmp_path, record):
    path = tmp_path / "bad.json"
    payload = json.dumps({**record, "contexte": []})
    path.write_text(payload)
    with running_app(server.create_app(baseline_dir=tmp_path)) as base:
        r = requests.get(base + "/api/baselines", timeout=5)
        assert r.status_code == 200 and r.json()["records"] == []
        assert "contexte" in r.json()["errors"][0]
    assert path.read_text() == payload


def test_backend_failure_does_not_leak_internal_details():
    def unavailable(text):
        raise RuntimeError("private implementation detail")
    with running_app(server.create_app(analyze=unavailable)) as base:
        for path in ("/api/analyze", "/api/compare"):
            body = {"question": EXAMPLE,
                    "record": {"question": "test", "reponse_ia": "test", "modele": "test", "date": "2026-11-14"}}
            r = requests.post(base + path, json=body, timeout=5)
            assert r.status_code == 503 and "private implementation" not in r.text
        r = requests.get(base + "/api/dossier.md", timeout=5)
        assert r.status_code == 503 and "error" in r.json()


def test_static_files_match_the_copied_front_and_paths_are_confined(web_api):
    base, _ = web_api
    root = Path(__file__).resolve().parent.parent
    response = requests.get(base + "/", timeout=5)
    assert response.content == (root / "web" / "index.html").read_bytes()
    for path in sorted((root / "web").rglob("*")):
        if path.is_file():
            url = "/assets/" + path.relative_to(root / "web").as_posix()
            r = requests.get(base + url, timeout=5)
            assert r.status_code == 200 and r.content == path.read_bytes(), url
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    for path in ("/assets/%2e%2e/server.py", "/assets/.env", "/assets/%2e%2e/data/trials.db"):
        assert requests.get(base + path, timeout=5).status_code == 404
    assert requests.get(base + "/api/analyze", timeout=5).status_code == 405
    assert requests.get(base + "/api/no-such-route", timeout=5).status_code == 404
