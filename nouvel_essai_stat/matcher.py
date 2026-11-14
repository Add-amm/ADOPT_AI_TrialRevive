"""Moteur d'appariement TrialRevive : étages 1, 2 et 4 (l'étage 3 se branche ensuite).

Principe : l'IA propose les fiches, ce code tranche. Tout verdict vient de règles
écrites ici, et chaque écart produit une phrase d'explication.

Usage : python matcher.py  (PostgreSQL par défaut)
        python matcher.py data/seh_kras_2009.json data/fiches_essais_fictives.json
"""
import json
import argparse
from pathlib import Path

import stats

NIVEAUX = ["E0", "E1", "E2", "E3", "E4"]
GAINS = [  # (code, libellé, niveau minimal), section 5.7.3
    ("G1", "Décision de poursuite ou d'arrêt accélérée", "E2"),
    ("G2", "Population mieux ciblée pour l'essai suivant", "E2"),
    ("G3", "Essai de confirmation de taille réduite", "E3"),
    ("G4", "Restriction ou sauvetage d'une indication", "E3"),
    ("G5", "Repositionnement ou relance, confirmation prospective requise", "E2"),
    ("G6", "Stratégie de diagnostic compagnon", "E3"),
]
# Paramètre à calibrer : un essai externe n'est pas vérifiable sur place.
PLAFOND_EXTERNE = "E3"
# Types de contraste de la base standardisée qui ne permettent pas de tester une interaction
CONTRASTES_EXCLUS = {"another_class_member", "same_treatment", "dose_schedule", "shorter_duration",
                     "none", "non_drug"}
# Champs que le registre ne donne pas : à remplir à la main ou par lecture IA validée.
CHAMPS_ETAGE2 = ["effectif_randomise", "bras", "prelevements", "taux_collecte_prevu", "taux_evenements_prevu", "consentement_portee"]


def niv(e):
    return NIVEAUX.index(e)


def min_niveau(a, b):
    return a if niv(a) <= niv(b) else b


def contrainte(seh, champ):
    return next((c for c in seh["contraintes"] if c["champ"] == champ), None)


# ---------------------------------------------------------------- étage 1
def _court(texte, n=80):
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def classes_traitement(f):
    t = f["traitement"]
    return set(t.get("classes") or ([t["classe"]] if t.get("classe") else []))


def etage1(seh, f):
    """Contraintes obligatoires lisibles sur la fiche. Renvoie la liste des raisons d'échec."""
    raisons = []
    c = contrainte(seh, "indication")
    if c and not any(m in f["indication"].lower() for m in c["valeur"]["inclut"]):
        raisons.append(f"indication hors champ ({_court(f['indication'])})")
    # stade inconnu (null) : non éliminatoire, à vérifier ; stade connu et différent : éliminatoire
    if c and c["valeur"].get("stade") and f.get("stade") not in (None, c["valeur"]["stade"]):
        raisons.append(f"maladie non métastatique (stade {f.get('stade')}, adjuvant ou local)")

    c = contrainte(seh, "date_debut")
    if c and f["date_debut"] >= c["valeur"]["avant"]:
        raisons.append(f"essai débuté le {f['date_debut']}, pas avant la date de l'hypothèse ({c['valeur']['avant']})")

    c = contrainte(seh, "comparateur")
    if c:
        if c["valeur"]["randomise"] and not f["randomise"]:
            raisons.append("pas de groupe contrôle tiré au sort")
        elif f.get("bras") is not None and len(f["bras"]) < 2:
            raisons.append("bras unique")
        classe_exclue = c["valeur"].get("exclut_classe")
        contraste = f["comparateur"].get("type_contraste")
        if contraste in CONTRASTES_EXCLUS:
            raisons.append(f"contraste entre bras inadapté ({contraste}) : pas de contrôle sans le traitement")
        bras = f.get("bras") or []
        if bras and all("classes" in b for b in bras):
            # lecture bras par bras : il faut au moins un bras sans la classe étudiée
            if all(classe_exclue in b["classes"] for b in bras):
                raisons.append(f"tous les bras reçoivent un {classe_exclue} : pas de contrôle sans {classe_exclue}")
        elif classe_exclue in f["comparateur"]["classes"]:
            raisons.append(f"le bras contrôle reçoit déjà un {classe_exclue}")

    c = contrainte(seh, "traitement")
    classe = c["tolere"]["classe"] if c else None
    if classe and classe not in classes_traitement(f):
        autres = ", ".join(sorted(classes_traitement(f))) or "aucune molécule de la classe trouvée"
        raisons.append(f"pas de {classe} étudié ({autres})")
    return raisons


# ---------------------------------------------------------------- étage 2
def score_temporel(intervalle_req, intervalle_essai, limite):
    """1 si recouvrement, 1 - d/t si 0 < d <= t, None (échec) si d > t (section 5.3.3)."""
    a1, b1 = intervalle_req
    a2, b2 = intervalle_essai
    d = max(0, a2 - b1, a1 - b2)
    if d == 0:
        return 1.0
    return 1 - d / limite if d <= limite else None


def bornes(v):
    """Une valeur simple ou une fourchette [bas, haut] -> (bas, haut)."""
    return (v[0], v[1]) if isinstance(v, (list, tuple)) else (v, v)


def etage2(seh, f):
    """Compatibilité structurelle et puissance a priori.

    Renvoie (ok, score, plafond, bonus_ideal, explications, details).
    """
    score, plafond, bonus, expl, details = 1.0, "E4", 0, [], {}

    manquants = [k for k in CHAMPS_ETAGE2 if f.get(k) is None]
    if manquants:
        return None, 0.0, "E0", 0, [f"fiche incomplète : {', '.join(manquants)}"], {"champs_manquants": manquants}

    def echec(msg):
        return False, 0.0, "E0", bonus, expl + [msg], details

    # traitement : molécule exacte ou même classe
    c = contrainte(seh, "traitement")
    mols = f["traitement"]["molecules"]
    s = max(c["table_substitution"].get(m, 0) for m in mols)
    if s == 0:
        return echec(f"molécule {mols} absente de la table de substitution")
    if any(m in c["ideal"]["molecules"] for m in mols):
        bonus += 1
    else:
        score *= s
        plafond = min_niveau(plafond, c["plafond_preuve"])
        expl.append(f"molécule {', '.join(mols)} au lieu de {', '.join(c['ideal']['molecules'])} "
                    f"(même classe) : score {s}, niveau plafonné à {c['plafond_preuve']} "
                    "tant qu'une réplication avec la molécule exacte manque")

    # critère de jugement
    c = contrainte(seh, "critere")
    meilleurs = [(c["table_substitution"][k], k) for k in f["criteres"] if k in c["table_substitution"]]
    if meilleurs:
        s, k = max(meilleurs)
        if k in c["ideal"]["valeurs"]:
            bonus += 1
        else:
            score *= s
            expl.append(f"critère {k} au lieu de {c['ideal']['valeurs'][0]} : score {s}")
    elif any(k in c["substitut"]["valeurs"] for k in f["criteres"]):
        score *= c["substitut"]["score"]
        plafond = min_niveau(plafond, c["substitut"]["plafond_preuve"])
        expl.append(f"critère substitué ({', '.join(f['criteres'])}) : niveau plafonné à "
                    f"{c['substitut']['plafond_preuve']} ; puissance calculée comme pour un critère "
                    "de survie, donc approximative")
    else:
        return echec(f"aucun critère de jugement compatible ({f['criteres']})")

    # matériel, instant, présence dans les deux bras
    cm, ci = contrainte(seh, "materiel"), contrainte(seh, "instant")
    noms_bras = {b["nom"] for b in f["bras"]}
    meilleur = None
    for p in f["prelevements"]:
        if p["materiel"] not in cm["valeur"]["types"]:
            continue
        s_t = score_temporel(ci["ideal"]["intervalle_j"], p["instant_j"], ci["fonction_tolerance"]["limite_j"])
        if s_t is None:
            continue
        deux_bras = noms_bras <= set(p["bras"])
        cand = (deux_bras, s_t, p)
        if meilleur is None or cand[:2] > meilleur[:2]:
            meilleur = cand
    if meilleur is None:
        return echec("aucun prélèvement de tissu tumoral fixé à un instant compatible")
    deux_bras, s_t, p = meilleur
    if not deux_bras:
        manquants = sorted(noms_bras - set(p["bras"]))
        return echec(f"tissu prévu seulement dans le(s) bras {', '.join(p['bras'])}, "
                     f"pas dans {', '.join(manquants)} : interaction non testable")
    if s_t == 1.0:
        bonus += 1
    else:
        score *= s_t
        expl.append(f"prélèvement hors de la fenêtre idéale : score {s_t:.2f}")
    details["prelevement_retenu"] = p

    # couverture prévue (valeur ou fourchette : la borne basse décide, par prudence)
    c = contrainte(seh, "couverture")
    cov, cov_haut = bornes(f["taux_collecte_prevu"])
    fourchette = cov != cov_haut
    details["couverture_prevue"] = f["taux_collecte_prevu"]
    if cov_haut < c["tolere"]["min"]:
        return echec(f"couverture prévue {cov_haut:.0%} < {c['tolere']['min']:.0%}")
    if cov >= c["ideal"]["min"]:
        bonus += 1
    else:
        plafond = min_niveau(plafond, c["plafond_preuve"])
        txt = f"{cov:.0%} à {cov_haut:.0%} (valeur par défaut, non vérifiée)" if fourchette else f"{cov:.0%}"
        expl.append(f"couverture prévue {txt}, sous {c['ideal']['min']:.0%} : "
                    f"niveau plafonné à {c['plafond_preuve']}")

    # consentement
    c = contrainte(seh, "consentement")
    s = c["table_substitution"].get(f["consentement_portee"], 0)
    if s == 0:
        return echec(f"consentement incompatible ({f['consentement_portee']})")
    if f["consentement_portee"] in c["ideal"]["valeurs"]:
        bonus += 1
    else:
        score *= s
        expl.append(f"portée du consentement {f['consentement_portee']} : à vérifier chez le détenteur (score {s})")

    # puissance a priori (5.6.2), en fourchette si une entrée est une fourchette
    e, x = seh["effets_attendus"], seh["exigence_statistique"]
    ev_bas, ev_haut = bornes(f["taux_evenements_prevu"])
    res = []
    for cv, ev in ((cov, ev_bas), (cov_haut, ev_haut)):
        d_plus, d_moins = stats.evenements_attendus(f["effectif_randomise"], e["prevalence_x"], cv, ev)
        res.append((stats.puissance_interaction(d_plus, d_moins, e["hr_x_plus"], e["hr_x_moins"], x["alpha"]),
                    round(d_plus), round(d_moins)))
    (pw, dp, dm), (pw_haut, dp_h, dm_h) = res
    incertain = pw_haut - pw > 0.005
    details["puissance_a_priori"] = {
        "valeur": round(pw, 3),
        "evenements_attendus": {"x_plus": dp, "x_moins": dm},
        "methode": "effectif × prévalence × couverture prévue × taux d'événements ; var ln(HR+/HR-) ≈ 4/d+ + 4/d-",
        "source": "calcul TrialRevive sur la fiche",
    }
    if incertain:
        details["puissance_a_priori"]["fourchette"] = [round(pw, 3), round(pw_haut, 3)]
        details["puissance_a_priori"]["evenements_attendus_haut"] = {"x_plus": dp_h, "x_moins": dm_h}
    if pw_haut < x["puissance"]:
        txt = f"{pw:.0%} à {pw_haut:.0%}" if incertain else f"{pw:.0%}"
        return echec(f"puissance a priori pour l'interaction {txt} < {x['puissance']:.0%} "
                     f"(environ {dp_h + dm_h} événements attendus au mieux)" if incertain else
                     f"puissance a priori pour l'interaction {txt} < {x['puissance']:.0%} "
                     f"(environ {dp + dm} événements attendus)")
    if pw < x["puissance"]:
        plafond = min_niveau(plafond, "E2")
        details["statut_puissance"] = "incertaine"
        expl.append(f"puissance incertaine : {pw:.0%} à {pw_haut:.0%} selon des valeurs par défaut ; "
                    "à confirmer dans les publications, niveau plafonné à E2")
    return True, score, plafond, bonus, expl, details


# ---------------------------------------------------------------- étage 4
def etage4(seh, f, plafond, details):
    bio = seh["biomarqueur_x"].split()[0]
    if bio in f.get("biomarqueurs_mesures", []):
        voie = ("R0", f"{bio} déjà mesuré dans les données")
    else:
        voie = ("R2", f"nouvelle analyse de {bio} sur le tissu archivé")

    niveau = "E3"  # randomisé, deux bras, puissance suffisante, couverture prévue >= tolérée
    conditions = ["fixer le plan d'analyse avant les mesures",
                  "utiliser une méthode de mesure validée"]
    if f["index"] == "externe":
        niveau = min_niveau(niveau, PLAFOND_EXTERNE)
        conditions.append("obtenir l'accès auprès du détenteur (vérification sur place impossible)")
    else:
        conditions.append("lancer l'étage 3 : compter les patients S4 chez le détenteur")
    niveau = min_niveau(niveau, plafond)
    if niveau == "E3":
        conditions.append("E4 si un second essai concordant est disponible")
    gains = [{"code": g, "libelle": l} for g, l, m in GAINS if niv(niveau) >= niv(m)]
    return {"voie": {"code": voie[0], "explication": voie[1]},
            "niveau_preuve_atteignable": niveau, "conditions_restantes": conditions, "gains": gains}


# ---------------------------------------------------------------- orchestration
def apparier(seh, fiches):
    exclus, retenus, a_completer = [], [], []
    for f in fiches:
        raisons = etage1(seh, f)
        if raisons:
            exclus.append({"trial_id": f["trial_id"], "titre": f["titre"], "etage": 1, "raisons": raisons})
            continue
        ok, score, plafond, bonus, expl, details = etage2(seh, f)
        if ok is None:
            a_completer.append({"trial_id": f["trial_id"], "titre": f["titre"], **details})
            continue
        if not ok:
            exclus.append({"trial_id": f["trial_id"], "titre": f["titre"], "etage": 2, "raisons": expl[-1:],
                           "ecarts_avant_exclusion": expl[:-1]})
            continue
        verdict = etage4(seh, f, plafond, details)
        retenus.append({"trial_id": f["trial_id"], "titre": f["titre"], "index": f["index"],
                        "detenteur": f["detenteur"], "score_compatibilite": round(score, 3),
                        "bonus_ideal": bonus, "effectif_randomise": f["effectif_randomise"],
                        "ecarts": expl, **details, **verdict,
                        "sources": f.get("sources", {})})

    cle = lambda r: (niv(r["niveau_preuve_atteignable"]), r["score_compatibilite"],
                     r["bonus_ideal"], r["effectif_randomise"])
    e = seh["effets_attendus"]
    x = seh["exigence_statistique"]
    return {
        "seh_id": seh["seh_id"], "version": seh["version"], "enonce": seh["enonce"],
        "exigence_statistique": {
            "evenements_min": round(stats.evenements_requis_interaction(
                e["hr_x_plus"], e["hr_x_moins"], e["prevalence_x"], x["alpha"], x["puissance"])),
            "methode": "(z1-a/2 + z1-b)^2 × 4 (1/p + 1/(1-p)) / (ln HR+ - ln HR-)^2", **x},
        "taille_essai_confirmation": stats.taille_essai_confirmation(
            e["hr_x_plus"], e["hr_x_moins"], e["prevalence_x"], x["alpha"], x["puissance"]),
        # jamais un classement commun (section 5.8)
        "internes": sorted([r for r in retenus if r["index"] == "interne"], key=cle, reverse=True),
        "externes": sorted([r for r in retenus if r["index"] == "externe"], key=cle, reverse=True),
        "exclus": exclus,
        "a_completer": a_completer,
        "n_essais_examines": len(fiches),
    }


def resume(res):
    lignes = [f"Hypothèse {res['seh_id']} v{res['version']} : {res['enonce']}",
              f"Exigence : {res['exigence_statistique']['evenements_min']} événements pour l'interaction",
              f"{res['n_essais_examines']} essais examinés"]
    for groupe in ("internes", "externes"):
        lignes.append(f"\n== Essais {groupe} retenus ({len(res[groupe])})")
        for i, r in enumerate(res[groupe], 1):
            p = r["puissance_a_priori"]
            pw = f"{p['fourchette'][0]:.0%} à {p['fourchette'][1]:.0%}" if "fourchette" in p else f"{p['valeur']:.0%}"
            lignes.append(f"{i}. {r['trial_id']} | {r['niveau_preuve_atteignable']} | {r['voie']['code']} | "
                          f"score {r['score_compatibilite']} | puissance {pw} | {r['titre']}")
            for ec in r["ecarts"]:
                lignes.append(f"     - {ec}")
    lignes.append(f"\n== Essais écartés ({len(res['exclus'])})")
    for x in res["exclus"]:
        lignes.append(f"- {x['trial_id']} (étage {x['etage']}) : {'; '.join(x['raisons'])}")
    if res["a_completer"]:
        lignes.append(f"\n== Passent l'étage 1 mais fiche à compléter ({len(res['a_completer'])})")
        for x in res["a_completer"]:
            lignes.append(f"- {x['trial_id']} : manque {', '.join(x['champs_manquants'])} | {x['titre']}")
    t = res["taille_essai_confirmation"]
    lignes.append(f"\nEssai de confirmation : {t['evenements_essai_tous']} événements ouvert à tous "
                  f"(HR dilué {t['hr_dilue_tous']}) contre {t['evenements_essai_x_plus']} réservé aux X+")
    return "\n".join(lignes)


def main(argv=None):
    racine = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seh", nargs="?", type=Path, default=racine / "data" / "seh_kras_2009.json")
    ap.add_argument("fiches", nargs="?", type=Path, help="ancien mode : fiches JSON explicites")
    ap.add_argument("resultat", nargs="?", type=Path, help="ancien chemin de sortie optionnel")
    ap.add_argument("--source", choices=("postgres", "fichier"), help="PostgreSQL par défaut si aucun fichier n'est fourni")
    ap.add_argument("--corpus", help="filtre du corpus pour la source PostgreSQL")
    ap.add_argument("--sortie", type=Path, help="fichier du résultat")
    a = ap.parse_args(argv)
    source = a.source or ("fichier" if a.fiches is not None else "postgres")
    if source == "postgres" and a.fiches is not None:
        ap.error("Ne fournissez pas de fichier de fiches avec --source postgres.")
    if source == "fichier" and a.fiches is None:
        ap.error("--source fichier nécessite un fichier de fiches JSON explicite.")
    if source == "fichier" and a.corpus:
        ap.error("--corpus s'applique à la source PostgreSQL ; filtrez le fichier explicitement.")
    from source_postgres import ErreurPostgres

    try:
        seh = json.loads(a.seh.read_text(encoding="utf-8"))
        if source == "postgres":
            from adaptateur_base import charger_fiches
            fiches = charger_fiches(corpus=a.corpus)
        else:
            fiches = json.loads(a.fiches.read_text(encoding="utf-8"))
    except (ErreurPostgres, OSError, ValueError) as exc:
        ap.exit(1, f"Chargement impossible : {exc}\n")
    res = apparier(seh, fiches)
    out = a.sortie or a.resultat or racine / "outputs" / "resultat_appariement.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(resume(res))
    print(f"\nRésultat complet : {out}")


if __name__ == "__main__":
    main()
