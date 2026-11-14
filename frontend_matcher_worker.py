"""Appelle le backend existant dans un processus isolé, sans le modifier.

L'isolation permet de garder ses imports locaux (stats, matcher, adaptateur_base)
sans les mélanger aux modules des anciennes interfaces.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "Backend"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seh", type=Path, required=True)
    parser.add_argument("--sortie", type=Path, required=True)
    parser.add_argument("--fiches", type=Path)
    parser.add_argument("--corpus")
    args = parser.parse_args()
    sys.path.insert(0, str(BACKEND))
    try:
        import matcher
        import adaptateur_base
        from source_postgres import ErreurPostgres
    except ImportError:
        args.sortie.write_text(json.dumps({"error": "Installez les dépendances avec python -m pip install -r requirements-web.txt."}), encoding="utf-8")
        return 1
    try:
        seh = json.loads(args.seh.read_text(encoding="utf-8"))
        fiches = (json.loads(args.fiches.read_text(encoding="utf-8")) if args.fiches is not None
                  else adaptateur_base.charger_fiches(corpus=args.corpus))
        resultat = matcher.apparier(seh, copy.deepcopy(fiches))
        # Métadonnées des mêmes fiches que celles sélectionnées par le backend.
        # Le critère de complétude est sa fonction existante, pas une nouvelle règle.
        uniques = {}
        for fiche in fiches:
            tid = fiche["trial_id"]
            if tid not in uniques or matcher._completude(fiche) > matcher._completude(uniques[tid]):
                uniques[tid] = fiche
        payload = {"seh": seh, "resultat": resultat, "fiches": list(uniques.values()),
                   "resume": matcher.resume(resultat)}
    except ErreurPostgres as exc:
        payload = {"error": f"Connexion du backend indisponible. Vérifiez Backend/.env. {exc}"}
    except (OSError, ValueError, KeyError, TypeError):
        payload = {"error": "Le backend n'a pas pu lire l'hypothèse ou les fiches. Vérifiez les entrées de Backend/matcher.py."}
    except Exception:
        payload = {"error": "Le backend n'a pas pu terminer l'appariement. Vérifiez ses entrées et ses dépendances."}
    args.sortie.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 1 if "error" in payload else 0


if __name__ == "__main__":
    raise SystemExit(main())
