"""Tests de source/CLI avec données fictives, sans accès à une base distante."""
import csv
import gzip
import json

import psycopg
import pytest

import adaptateur_base
import matcher
import source_postgres as pg
from test_trialrevive import _rec


def test_default_connection_targets_project_without_hardcoded_password():
    opts = pg.options_connexion({"PGPASSWORD": "fixture-only"})
    assert opts["host"] == pg.HOTE_DEFAUT
    assert opts["port"] == "5432" and opts["user"] == opts["dbname"] == "postgres"
    assert opts["sslmode"] == "verify-full" and opts["sslrootcert"]
    assert opts["connect_timeout"] == 10


def test_url_is_configurable_and_cannot_disable_tls_verification():
    opts = pg.options_connexion({"DATABASE_URL": "postgresql://reader:fixture-only@database.example:6543/custom?sslmode=disable"})
    assert opts["host"] == "database.example" and opts["port"] == "6543"
    assert opts["dbname"] == "custom" and opts["user"] == "reader"
    assert opts["sslmode"] == "verify-full"


def test_missing_secret_is_explicit_not_demo_fallback():
    with pytest.raises(pg.ErreurPostgres, match="DATABASE_URL ou PGPASSWORD"):
        pg.options_connexion({})


def test_invalid_dsn_never_leaks_its_value():
    with pytest.raises(pg.ErreurPostgres) as err:
        pg.options_connexion({"DATABASE_URL": "secret-fixture-invalid-dsn"})
    assert "secret-fixture" not in str(err.value)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute(self, query):
        assert self.connection.read_only and self.connection.timeout_set
        self.query = query.as_string()

    def __iter__(self):
        return iter(self.connection.rows)


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.read_only = False
        self.timeout_set = False
        self.closed = False
        self.reader = Cursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute(self, statement):
        assert self.read_only
        assert statement == "SET LOCAL statement_timeout = '30s'"
        self.timeout_set = True

    def cursor(self, name):
        assert name == "trialrevive_fiches"
        return self.reader


def fake_connection(monkeypatch, rows):
    connection = Connection(rows)
    monkeypatch.setattr(pg, "charger_environnement", lambda: None)
    monkeypatch.setattr(pg, "options_connexion", lambda: {"host": "fixture-only"})
    monkeypatch.setattr(psycopg, "connect", lambda **opts: connection)
    return connection


def test_reads_only_json_column_in_readonly_transaction(monkeypatch):
    a, b = _rec("FICTIF-A", 1100), _rec("FICTIF-B", 400)
    conn = fake_connection(monkeypatch, [(a,), (json.dumps(b),)])
    rows = list(pg.lire_postgres(schema="public", table="trials", colonne="json"))
    assert rows == [a, b]
    assert conn.reader.query == 'SELECT "json" FROM "public"."trials"'
    assert conn.reader.itersize == 500
    assert conn.closed and conn.reader.closed


def test_table_and_column_names_are_quoted_as_identifiers(monkeypatch):
    conn = fake_connection(monkeypatch, [])
    list(pg.lire_postgres(schema="dataset", table='trials"; DROP TABLE trials;--', colonne="payload"))
    assert conn.reader.query == 'SELECT "payload" FROM "dataset"."trials""; DROP TABLE trials;--"'


@pytest.mark.parametrize("value", [None, [], 123, "private-fixture-invalid-json"])
def test_invalid_json_rows_fail_and_close_resources_without_logging_data(monkeypatch, value):
    conn = fake_connection(monkeypatch, [(value,)])
    with pytest.raises(pg.ErreurPostgres) as err:
        list(pg.lire_postgres())
    assert "private-fixture" not in str(err.value)
    assert conn.closed and conn.reader.closed


def test_driver_failure_is_redacted(monkeypatch):
    monkeypatch.setattr(pg, "charger_environnement", lambda: None)
    monkeypatch.setattr(pg, "options_connexion", lambda: {})
    def unavailable(**kwargs):
        raise psycopg.OperationalError("password=private-fixture-credential")
    monkeypatch.setattr(psycopg, "connect", unavailable)
    with pytest.raises(pg.ErreurPostgres) as err:
        list(pg.lire_postgres())
    assert "private-fixture" not in str(err.value)
    assert "impossible" in str(err.value)


@pytest.mark.parametrize("suffix", [".csv", ".jsonl", ".jsonl.gz"])
def test_explicit_file_formats_remain_available(tmp_path, suffix):
    record = _rec("FICTIF-FILE", 1100)
    path = tmp_path / ("records" + suffix)
    if suffix == ".csv":
        with path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, ["json"])
            writer.writeheader()
            writer.writerow({"json": json.dumps(record)})
    elif suffix.endswith(".gz"):
        with gzip.open(path, "wt", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
    else:
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert list(adaptateur_base.lire(path)) == [record]
    assert adaptateur_base.charger_fiches(path) == [adaptateur_base.vers_fiche(record)]


def test_postgres_and_file_conversion_have_identical_matching_results(monkeypatch, tmp_path):
    records = [_rec("FICTIF-LARGE", 1100), _rec("FICTIF-SMALL", 150)]
    monkeypatch.setattr(adaptateur_base, "lire_postgres", lambda: iter(records + records + [{"record_type": "document"}]))
    fiches = adaptateur_base.charger_fiches(corpus="kras")
    assert fiches == [adaptateur_base.vers_fiche(r) for r in records]
    seh = json.loads((pg.RACINE / "data/seh_kras_2009.json").read_text())
    expected = matcher.apparier(seh, fiches)
    out = tmp_path / "result.json"
    matcher.main(["--corpus", "kras", "--sortie", str(out)])
    assert json.loads(out.read_text()) == expected
    assert expected["n_essais_examines"] == 2


def test_adapter_cli_uses_postgres_without_input_file(monkeypatch, tmp_path):
    record = _rec("FICTIF-CLI", 1100)
    monkeypatch.setattr(adaptateur_base, "lire_postgres", lambda: iter([record]))
    out = tmp_path / "subdir/fiches.json"
    adaptateur_base.main(["--sortie", str(out)])
    assert json.loads(out.read_text()) == [adaptateur_base.vers_fiche(record)]


def test_cli_connection_failure_does_not_create_fake_result(monkeypatch, tmp_path, capsys):
    def failed():
        raise pg.ErreurPostgres("Connexion PostgreSQL impossible.")
    monkeypatch.setattr(adaptateur_base, "lire_postgres", failed)
    out = tmp_path / "result.json"
    with pytest.raises(SystemExit) as err:
        matcher.main(["--sortie", str(out)])
    assert err.value.code == 1 and not out.exists()
    assert "Connexion PostgreSQL impossible" in capsys.readouterr().err


def test_legacy_fictitious_file_cli_is_unchanged(tmp_path, monkeypatch):
    def no_database():
        pytest.fail("Le mode fichier ne doit pas interroger PostgreSQL")
    monkeypatch.setattr(adaptateur_base, "lire_postgres", no_database)
    seh = pg.RACINE / "data/seh_kras_2009.json"
    fiches = pg.RACINE / "data/fiches_essais_fictives.json"
    out = tmp_path / "legacy.json"
    matcher.main([str(seh), str(fiches), str(out)])
    assert json.loads(out.read_text()) == matcher.apparier(json.loads(seh.read_text()), json.loads(fiches.read_text()))
