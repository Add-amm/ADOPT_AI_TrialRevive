"""Entrée PostgreSQL automatique, sans modifier le moteur VF_stats ni appeler Supabase."""
import copy
import json
import os
import ssl
from pathlib import Path

import pytest

import adaptateur_base
import matcher
import source_postgres as pg
from test_trialrevive import _rec


def question_locale():
    return json.loads((Path(__file__).parent / "data/seh_kras_2009.json").read_text())


def test_default_cli_uses_database_and_keeps_vf_specific_results(monkeypatch, tmp_path):
    records = [_rec("FICTIF-GRAND", 1100), _rec("FICTIF-PETIT", 150)]
    waiting = _rec("FICTIF-EN-COURS", 900)
    waiting["dates"].update(start="2009-06-01", first_posted="2008-03-01")
    selected = _rec("FICTIF-SELECTIONNE", 900)
    selected["population"] = {"biomarker_selected": ["KRAS"]}
    records += [waiting, selected]
    monkeypatch.setattr(adaptateur_base, "lire_postgres", lambda: iter(copy.deepcopy(records)))
    expected = matcher.apparier(question_locale(), [adaptateur_base.vers_fiche(r) for r in copy.deepcopy(records)])
    out = tmp_path / "result.json"
    matcher.main(["--sortie", str(out)])
    result = json.loads(out.read_text())
    assert result == expected
    assert result["en_cours"][0]["trial_id"] == "FICTIF-EN-COURS"
    assert any(r["trial_id"] == "FICTIF-SELECTIONNE" for r in result["exclus"])


def test_database_duplicates_reach_the_vf_completeness_selection(monkeypatch, tmp_path):
    incomplete = _rec("FICTIF-DUPLICATE", None, tissue=False)
    complete = _rec("FICTIF-DUPLICATE", 1100)
    # Même identifiant ET même corpus : le premier enregistrement ne doit pas
    # éliminer la fiche complète avant que VF_stats ne puisse la sélectionner.
    monkeypatch.setattr(adaptateur_base, "lire_postgres", lambda: iter([incomplete, complete]))
    fiches = adaptateur_base.charger_fiches()
    assert len(fiches) == 2
    out = tmp_path / "duplicates.json"
    matcher.main(["--sortie", str(out)])
    result = json.loads(out.read_text())
    assert result["n_lignes_recues"] == 2 and result["n_essais_examines"] == 1
    assert result["externes"][0]["effectif_randomise"] == 1100
    assert not result["a_completer"]


def test_corpus_filter_and_record_types_apply_to_database(monkeypatch, tmp_path):
    keep = _rec("FICTIF-GARDE", 1100)
    other = _rec("FICTIF-AUTRE", 1100)
    other["provenance"]["corpus"] = "autre_domaine"
    monkeypatch.setattr(adaptateur_base, "lire_postgres", lambda: iter([keep, other, {"record_type": "document"}]))
    out = tmp_path / "filtered.json"
    matcher.main(["--corpus", "kras", "--sortie", str(out)])
    result = json.loads(out.read_text())
    assert result["n_lignes_recues"] == 1
    assert result["externes"][0]["trial_id"] == "FICTIF-GARDE"


def test_file_mode_does_not_open_database(monkeypatch, tmp_path):
    def no_database():
        pytest.fail("Le fichier explicite doit fonctionner sans PostgreSQL")
    monkeypatch.setattr(adaptateur_base, "lire_postgres", no_database)
    folder = Path(__file__).parent
    question = folder / "data/seh_kras_2009.json"
    fiches = folder / "data/fiches_essais_fictives.json"
    out = tmp_path / "legacy.json"
    matcher.main([str(question), str(fiches), str(out)])
    assert json.loads(out.read_text()) == matcher.apparier(question_locale(), json.loads(fiches.read_text()))


def test_database_failure_never_falls_back_to_demo(monkeypatch, tmp_path, capsys):
    def failed():
        raise pg.ErreurPostgres("Connexion PostgreSQL impossible.")
    monkeypatch.setattr(adaptateur_base, "lire_postgres", failed)
    out = tmp_path / "failed.json"
    with pytest.raises(SystemExit) as err:
        matcher.main(["--sortie", str(out)])
    assert err.value.code == 1 and not out.exists()
    assert "Connexion PostgreSQL impossible" in capsys.readouterr().err


def test_adapter_cli_has_automatic_database_input(monkeypatch, tmp_path):
    record = _rec("FICTIF-ADAPTATEUR", 1100)
    monkeypatch.setattr(adaptateur_base, "lire_postgres", lambda: iter([record]))
    out = tmp_path / "subdir/fiches.json"
    adaptateur_base.main(["--sortie", str(out)])
    assert json.loads(out.read_text()) == [adaptateur_base.vers_fiche(record)]


@pytest.mark.parametrize("args", [["--source", "fichier"],
                                  ["a.json", "b.json", "--source", "postgres"],
                                  ["a.json", "b.json", "--corpus", "kras"]])
def test_inconsistent_sources_fail_before_loading(args):
    with pytest.raises(SystemExit) as err:
        matcher.main(args)
    assert err.value.code == 2


def test_pooler_configuration_keeps_tls_and_vf_local_certificate():
    opts = pg.options_connexion({
        "DATABASE_URL": "postgresql://reader:fixture-only@aws-1-eu-west-1.pooler.supabase.com:5432/postgres",
        "PGHOST": "old.example", "PGUSER": "old-user", "PGPASSWORD": "",
    })
    assert opts["host"] == "aws-1-eu-west-1.pooler.supabase.com" and opts["user"] == "reader"
    assert opts["sslmode"] == "verify-full"
    assert Path(opts["sslrootcert"]) == pg.CA_SUPABASE
    context = ssl.create_default_context(cafile=opts["sslrootcert"])
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


@pytest.mark.parametrize("kind", ["process", "vf", "reference", "root"])
def test_configuration_priority_without_copying_credentials(monkeypatch, tmp_path, kind):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    root = tmp_path / "project"
    vf = root / "VF_stats"
    reference = root / "nouvel_essai_stat"
    vf.mkdir(parents=True)
    reference.mkdir()
    (root / ".env").write_text("DATABASE_URL=root-fixture\n")
    if kind in ("process", "vf", "reference"):
        (reference / ".env").write_text("DATABASE_URL=reference-fixture\n")
    if kind in ("process", "vf"):
        (vf / ".env").write_text("DATABASE_URL=vf-fixture\n")
    monkeypatch.setattr(pg, "RACINE", vf)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if kind == "process":
        monkeypatch.setenv("DATABASE_URL", "process-fixture")
    pg.charger_environnement()
    assert os.environ["DATABASE_URL"] == kind + "-fixture"


def test_explicit_vf_file_does_not_mix_in_another_database_url(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    root = tmp_path / "project"
    vf = root / "VF_stats"
    reference = root / "nouvel_essai_stat"
    vf.mkdir(parents=True)
    reference.mkdir()
    (vf / ".env").write_text("PGPASSWORD=vf-fixture\n")
    (reference / ".env").write_text("DATABASE_URL=reference-fixture\n")
    monkeypatch.setattr(pg, "RACINE", vf)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PGPASSWORD", raising=False)
    pg.charger_environnement()
    assert "DATABASE_URL" not in os.environ
    assert os.environ["PGPASSWORD"] == "vf-fixture"
