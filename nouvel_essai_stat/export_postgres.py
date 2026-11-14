"""Exporte la base Postgres de l'équipe (Supabase), en LECTURE SEULE, et décrit sa structure.

À lancer sur Onyxia :
    pip install psycopg2-binary
    export DATABASE_URL="postgresql://postgres:MOT_DE_PASSE@db.<projet>.supabase.co:5432/postgres"
    python3 export_postgres.py

Le mot de passe reste dans la variable d'environnement : il n'est écrit dans aucun fichier.

Produit :
    data/supabase/<schema>.<table>.csv   le contenu de chaque table
    data/supabase/schema.txt             tables, colonnes, liens, exemples : à m'envoyer
"""
import os
import sys

import psycopg2

URL = os.environ.get("DATABASE_URL")
OUT = "data/supabase"
SCHEMAS_SYSTEME = ("pg_catalog", "information_schema", "auth", "storage", "realtime", "extensions",
                   "graphql", "graphql_public", "pgsodium", "pgsodium_masks", "vault", "supabase_functions",
                   "supabase_migrations", "net", "cron", "pgbouncer", "_realtime", "_analytics")


def main():
    if not URL:
        sys.exit('Définis d\'abord : export DATABASE_URL="postgresql://postgres:MOT_DE_PASSE@..."')
    try:
        conn = psycopg2.connect(URL, connect_timeout=20)
    except psycopg2.OperationalError as e:
        sys.exit(f"Connexion impossible :\n{e}\n"
                 "Si l'erreur parle d'adresse réseau ou d'IPv6, utilise l'adresse « Session pooler » "
                 "de Supabase (bouton Connect du projet) à la place de db.<projet>.supabase.co.")
    conn.set_session(readonly=True, autocommit=True)  # aucune écriture possible
    cur = conn.cursor()
    os.makedirs(OUT, exist_ok=True)

    cur.execute("""SELECT table_schema, table_name FROM information_schema.tables
                   WHERE table_type IN ('BASE TABLE', 'VIEW') AND table_schema NOT IN %s
                   ORDER BY 1, 2""", (SCHEMAS_SYSTEME,))
    tables = cur.fetchall()
    cur.execute("""SELECT tc.table_schema, tc.table_name, kcu.column_name,
                          ccu.table_schema, ccu.table_name, ccu.column_name
                   FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                   JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                   WHERE tc.constraint_type = 'FOREIGN KEY'""")
    liens = {}
    for s, t, c, s2, t2, c2 in cur.fetchall():
        liens[(s, t, c)] = f"{s2}.{t2}.{c2}"

    lignes = [f"{len(tables)} tables ou vues", ""]
    for schema, table in tables:
        nom = f'"{schema}"."{table}"'
        cur.execute(f"SELECT count(*) FROM {nom}")
        n = cur.fetchone()[0]
        lignes.append(f"## {schema}.{table} : {n} lignes")
        cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                       WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position""", (schema, table))
        colonnes = cur.fetchall()
        cur.execute(f"SELECT * FROM {nom} LIMIT 1000")
        echantillon = cur.fetchall()
        for i, (col, typ) in enumerate(colonnes):
            valeurs = [r[i] for r in echantillon]
            vides = sum(v in (None, "", [], {}) for v in valeurs)
            exemples = []
            for v in valeurs:
                if v not in (None, "", [], {}) and str(v)[:60] not in exemples:
                    exemples.append(str(v)[:60])
                if len(exemples) == 3:
                    break
            lien = f" → {liens[(schema, table, col)]}" if (schema, table, col) in liens else ""
            part = f"{vides}/{len(valeurs)} vides (sur 1000 lignes max)" if valeurs else "table vide"
            lignes.append(f"  - {col} ({typ}){lien} · {part} · ex. : {' | '.join(exemples)}")
        lignes.append("")
        with open(f"{OUT}/{schema}.{table}.csv", "w") as f:
            cur.copy_expert(f"COPY (SELECT * FROM {nom}) TO STDOUT WITH CSV HEADER", f)
        print(f"{schema}.{table} : {n} lignes")

    open(f"{OUT}/schema.txt", "w").write("\n".join(lignes))
    conn.close()
    print(f"\nStructure écrite dans {OUT}/schema.txt : relis-la, puis envoie-la-moi.")


if __name__ == "__main__":
    main()
