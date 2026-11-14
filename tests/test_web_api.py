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
from src import compare, dossier, engine, fake_data, question
from web_adapter import adapt_dossier, analyze, json_value


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
    with running_app(server.create_app(baseline_dir=directory)) as base:
        yield base, directory


@pytest.fixture
def record():
    return {"question": question.CAS_VEDETTE_TEXTE,
            "modele": "Fixture de test uniquement", "date": "2026-11-14",
            "reponse_ia": "  NCT00364013 et NCT99999999.\n<script>window.injected=true</script>\n"}


def test_routes_use_our_pipeline_without_changing_business_results(web_api):
    base, _ = web_api
    card = question.parse_question(question.CAS_VEDETTE_TEXTE)
    screening = engine.screen_trials(card, engine.load_cvs())
    usable = engine.count_usable(fake_data.load(), card)
    raw = dossier.build_dossier(card, screening, engine.rejection_summary(screening), usable,
                                engine.group_summary(usable["data"], card))
    response = requests.post(base + "/api/analyze", json={"question": card["question"]}, timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert data["exemple"] == card["question"]
    assert data["markdown"] == dossier.to_markdown(raw)
    # La passerelle n'ajoute que des champs inconnus ; chaque valeur calculée reste identique.
    def included(expected, actual):
        if isinstance(expected, dict):
            for key, value in expected.items():
                included(value, actual[key])
        elif isinstance(expected, list):
            assert len(expected) == len(actual)
            for x, y in zip(expected, actual):
                included(x, y)
        else:
            assert expected == actual
    included(json_value(raw), data["dossier"])
    d = data["dossier"]
    assert d["rejection"]["total"] == 104 and len(d["retenus"]) == 6 and d["utilisables"] == 252
    assert d["verdict"]["preuve_verifiee"] is False


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
    assert requests.get(base + "/api/info", timeout=5).json() == {"exemple": question.CAS_VEDETTE_TEXTE}
    r = requests.get(base + "/api/dossier.md", params={"question": question.CAS_VEDETTE_TEXTE}, timeout=5)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text == analyze(question.CAS_VEDETTE_TEXTE)["markdown"]


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


def test_other_drug_does_not_invent_an_internal_arm(web_api):
    base, _ = web_api
    r = requests.post(base + "/api/analyze", json={"question": "Le statut KRAS change-t-il l'effet du cetuximab ?"}, timeout=5)
    assert r.status_code == 200
    d = r.json()["dossier"]
    assert d["utilisables"] is None and "aucun bras cetuximab" in d["raison_indetermination"]


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
    assert ncts["NCT00364013"] == "Présent" and ncts["NCT99999999"].startswith("Absent")
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
            body = {"question": question.CAS_VEDETTE_TEXTE,
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
