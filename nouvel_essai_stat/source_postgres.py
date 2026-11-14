"""Lecture seule du corpus standardisé PostgreSQL (colonne JSON/JSONB).

Les identifiants non secrets du projet sont les valeurs par défaut. Le secret
vient exclusivement de DATABASE_URL ou PGPASSWORD, jamais du code source.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path

HOTE_DEFAUT = "db.rnlfbeksplyoywweoddo.supabase.co"
RACINE = Path(__file__).resolve().parent


class ErreurPostgres(RuntimeError):
    """Diagnostic public sans URI, mot de passe ou contenu de ligne."""


def charger_environnement():
    from dotenv import load_dotenv

    # Les variables déjà injectées sont prioritaires sur les fichiers locaux.
    load_dotenv(RACINE / ".env", override=False)
    load_dotenv(RACINE.parent / ".env", override=False)


def options_connexion(environ=None):
    import certifi
    from psycopg.conninfo import conninfo_to_dict

    env = os.environ if environ is None else environ
    url = env.get("DATABASE_URL")
    try:
        opts = conninfo_to_dict(url) if url else {}
    except Exception:
        raise ErreurPostgres("DATABASE_URL invalide. Vérifiez sa syntaxe sans publier sa valeur.") from None
    for key, name, default in (("host", "PGHOST", HOTE_DEFAUT), ("port", "PGPORT", "5432"),
                               ("dbname", "PGDATABASE", "postgres"), ("user", "PGUSER", "postgres")):
        opts.setdefault(key, env.get(name) or default)
    opts.setdefault("password", env.get("PGPASSWORD"))
    if not opts.get("password"):
        raise ErreurPostgres("Configurez DATABASE_URL ou PGPASSWORD dans l'environnement ou dans "
                             "nouvel_essai_stat/.env (ignoré par Git). Aucun mot de passe n'est fourni par défaut.")
    # Ne jamais faire de repli TLS non vérifié, même si l'URI le demande.
    opts["sslmode"] = "verify-full"
    opts.setdefault("sslrootcert", env.get("PGSSLROOTCERT") or certifi.where())
    opts["connect_timeout"] = 10
    opts["application_name"] = "trialrevive-stat-lecture"
    return opts


@contextmanager
def connexion_lecture_seule():
    import psycopg

    charger_environnement()
    opts = options_connexion()
    try:
        with psycopg.connect(**opts) as conn:
            conn.read_only = True
            # La première transaction commence en READ ONLY, avant toute lecture.
            conn.execute("SET LOCAL statement_timeout = '30s'")
            yield conn
    except psycopg.Error as exc:
        code = getattr(exc, "sqlstate", None)
        if code in ("42P01", "42703", "3F000"):
            message = ("Table ou colonne PostgreSQL introuvable. Vérifiez PG_TRIALS_SCHEMA, "
                       "PG_TRIALS_TABLE et PG_TRIALS_JSON_COLUMN.")
        elif code in ("28P01", "28000", "42501"):
            message = "Authentification ou droits de lecture PostgreSQL refusés."
        else:
            message = ("Connexion ou lecture PostgreSQL impossible. Vérifiez le réseau, l'hôte, "
                       "les identifiants et le certificat TLS ; aucun repli vers des données fictives n'est effectué.")
        raise ErreurPostgres(message) from None


def lire_postgres(*, schema=None, table=None, colonne=None):
    """Itère sur la seule colonne standardisée, par lots, sans export des tables."""
    from psycopg import sql

    charger_environnement()
    schema = schema or os.getenv("PG_TRIALS_SCHEMA", "public")
    table = table or os.getenv("PG_TRIALS_TABLE", "trials")
    colonne = colonne or os.getenv("PG_TRIALS_JSON_COLUMN", "json")
    requete = sql.SQL("SELECT {colonne} FROM {schema}.{table}").format(
        colonne=sql.Identifier(colonne), schema=sql.Identifier(schema), table=sql.Identifier(table))
    with connexion_lecture_seule() as conn:
        with conn.cursor(name="trialrevive_fiches") as cur:
            cur.itersize = 500
            cur.execute(requete)
            for numero, row in enumerate(cur, 1):
                value = row[0]
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        raise ErreurPostgres(f"JSON invalide dans la ligne lue n°{numero} (contenu non affiché).") from None
                if not isinstance(value, dict):
                    raise ErreurPostgres(f"La ligne lue n°{numero} ne contient pas un objet JSON standardisé.")
                yield value
