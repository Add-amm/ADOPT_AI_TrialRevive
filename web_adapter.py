"""Adaptation HTTP du backend local, sans modification des modules src/.

Le format est celui de docs/CONTRAT_API.md, consommé par web/js/app.js.
Les valeurs manquantes restent inconnues : aucun calcul métier ajouté ici.
"""
import math
from collections.abc import Mapping
from copy import deepcopy

import numpy as np

from src import dossier, engine, fake_data, question


def json_value(value):
    """Valeurs JSON strictes : NaN/inf et scalaires numpy ne fuient pas dans l'API."""
    if isinstance(value, np.generic):
        return json_value(value.item())
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    raise TypeError(f"Valeur non sérialisable : {type(value).__name__}")


def with_defaults(value, defaults):
    result = deepcopy(value) if isinstance(value, dict) else {}
    for key, default in defaults.items():
        if key not in result:
            result[key] = deepcopy(default)
    return result


def adapt_dossier(result: dict) -> dict:
    """Préserve les données calculées ; complète seulement la structure attendue.

    null = inconnu, [] = aucune entrée disponible, « non calculé » = texte absent.
    Les niveaux E/R ne sont jamais recalculés ou promus par cet adaptateur.
    """
    out = with_defaults(result, {
        "question": "non calculé", "retenus": [], "ecartes": [], "entonnoir": [],
        "utilisables": None, "statut_comptage": "non calculé", "raison_indetermination": None,
        "groupes": [], "methode": "non calculé", "sources": [], "limites": [],
    })
    out["rejection"] = with_defaults(out.get("rejection"), {
        "total": None, "retenus": None, "ecartes_par_etape": {},
    })
    out["verdict"] = with_defaults(out.get("verdict"), {
        "R": "non calculé", "R_texte": "non calculé", "E": "non calculé",
        "E_texte": "non calculé", "E_pourquoi": "non calculé", "G": [], "preuve_verifiee": None,
    })
    out["statistique"] = with_defaults(out.get("statistique"), {
        "evenements_necessaires_par_groupe": None, "evenements_internes": {},
        "suffisant": None, "hr_hypothese": None,
    })
    out["essai_confirmation"] = with_defaults(out.get("essai_confirmation"), {
        "hr_dilue": None, "evenements_tous": None, "evenements_selectionnes": None,
    })
    out["gain"] = with_defaults(out.get("gain"), {
        "pct_sauvage": None, "gain_sauvage_mois": None, "gain_mute_mois": None, "note": "non calculé",
    })
    trial_defaults = {
        "nct_id": None, "titre": "non calculé", "lien": None, "nb_patients": None,
        "retenu": None, "niveau": None, "etape_rejet": None, "raison": "non calculé",
        "score": None, "plafond": "non calculé", "bonus": None, "couverture": None,
        "ecarts": [], "reanalyse_verifiee": None, "n_kras_evalue": None,
        "E": "non calculé", "R": "non calculé", "R_pourquoi": "non calculé", "conditions": [],
    }
    for key in ("retenus", "ecartes"):
        out[key] = [with_defaults(row, trial_defaults) for row in (out[key] or [])]
    out["entonnoir"] = [with_defaults(row, {"etape": "non calculé", "n": None, "n_publie": None})
                        for row in (out["entonnoir"] or [])]
    out["groupes"] = [with_defaults(row, {
        "statut": "non calculé", "n_traite": None, "n_controle": None,
        "mediane_traite": None, "mediane_controle": None, "evenements": None, "gain_mois": None,
    }) for row in (out["groupes"] or [])]
    out["sources"] = [with_defaults(row, {
        "nct_id": None, "lien": None, "niveau": None, "reanalyse": None,
        "publication_lien": None, "reanalyse_verifiee": None,
    }) for row in (out["sources"] or [])]
    return json_value(out)


def analyze(text: str) -> dict:
    """Même pipeline que les interfaces Streamlit, appelé directement sans leur UI."""
    card = question.parse_question(text)
    screening = engine.screen_trials(card, engine.load_cvs())
    usable = engine.count_usable(fake_data.load(), card)
    groups = engine.group_summary(usable["data"], card)
    raw = dossier.build_dossier(card, screening, engine.rejection_summary(screening), usable, groups)
    return {"dossier": adapt_dossier(raw), "markdown": dossier.to_markdown(raw),
            "exemple": question.CAS_VEDETTE_TEXTE}
