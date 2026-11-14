"""Calculs statistiques déterministes de TrialRevive (aucune IA ici).

Références : description technique, sections 5.3.5 (exigence statistique),
5.6.2 (puissance a priori), 5.6.3 (masquage, représentativité), 5.7.4 (Schoenfeld).
"""
from math import log, sqrt, ceil

from scipy.stats import norm


def _z(alpha, puissance):
    return norm.ppf(1 - alpha / 2), norm.ppf(puissance)


def evenements_requis_interaction(hr_x_plus, hr_x_moins, prevalence_x, alpha=0.05, puissance=0.80):
    """Nombre total d'événements pour détecter l'interaction (section 5.3.5).

    Variance de ln(HR+/HR-) ≈ 4/d+ + 4/d-, avec d+ = d·p et d- = d·(1-p).
    """
    za, zb = _z(alpha, puissance)
    effet = (log(hr_x_plus) - log(hr_x_moins)) ** 2
    return (za + zb) ** 2 * 4 * (1 / prevalence_x + 1 / (1 - prevalence_x)) / effet


def puissance_interaction(d_plus, d_moins, hr_x_plus, hr_x_moins, alpha=0.05):
    """Puissance du test d'interaction bilatéral pour d+ et d- événements."""
    if d_plus <= 0 or d_moins <= 0:
        return 0.0
    za = norm.ppf(1 - alpha / 2)
    es = sqrt(4 / d_plus + 4 / d_moins)
    return float(norm.cdf(abs(log(hr_x_plus) - log(hr_x_moins)) / es - za))


def evenements_attendus(effectif, prevalence_x, taux_collecte, taux_evenements):
    """Estimation a priori de d+ et d- (section 5.6.2)."""
    total = effectif * taux_collecte * taux_evenements
    return total * prevalence_x, total * (1 - prevalence_x)


def schoenfeld(hr, alpha=0.05, puissance=0.80):
    """Événements requis pour un essai de confirmation, randomisation 1:1 (5.7.4)."""
    za, zb = _z(alpha, puissance)
    return 4 * (za + zb) ** 2 / log(hr) ** 2


def hr_dilue(hr_x_plus, hr_x_moins, prevalence_x):
    """HR approché chez tous les patients (moyenne des log-HR pondérée)."""
    from math import exp
    return exp(prevalence_x * log(hr_x_plus) + (1 - prevalence_x) * log(hr_x_moins))


def taille_essai_confirmation(hr_x_plus, hr_x_moins, prevalence_x, alpha=0.05, puissance=0.80):
    """Compare un essai ouvert à tous et un essai réservé aux X+ (5.7.4)."""
    hr_tous = hr_dilue(hr_x_plus, hr_x_moins, prevalence_x)
    res = {
        "hr_dilue_tous": round(hr_tous, 3),
        "evenements_essai_tous": ceil(schoenfeld(hr_tous, alpha, puissance)) if hr_tous != 1 else None,
        "evenements_essai_x_plus": ceil(schoenfeld(hr_x_plus, alpha, puissance)),
        "hypotheses": {"hr_x_plus": hr_x_plus, "hr_x_moins": hr_x_moins,
                       "prevalence_x": prevalence_x, "alpha": alpha, "puissance": puissance},
        "methode": "Schoenfeld, randomisation 1:1",
    }
    return res


def difference_standardisee(m1, s1, m2, s2):
    """Différence standardisée (SMD) entre deux groupes pour une variable continue."""
    pooled = sqrt((s1 ** 2 + s2 ** 2) / 2)
    return 0.0 if pooled == 0 else abs(m1 - m2) / pooled


def difference_standardisee_proportion(p1, p2):
    pooled = sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / 2)
    return 0.0 if pooled == 0 else abs(p1 - p2) / pooled


def masquer_cascade(cascade, seuil=5):
    """Masque les effectifs < seuil, y compris par soustraction (suppression secondaire).

    cascade : dict bras -> liste ordonnée d'effectifs [S0, S1, S2, S3, S4].
    Renvoie la même structure où les valeurs masquées valent "<seuil".
    """
    bras = list(cascade)
    masque = {b: [False] * len(cascade[b]) for b in bras}
    for b in bras:
        vals = cascade[b]
        for i, v in enumerate(vals):
            if 0 < v < seuil:
                masque[b][i] = True
            # une différence entre étapes < seuil révèle un petit effectif
            if i > 0 and 0 < vals[i - 1] - v < seuil:
                masque[b][i] = True
    # entre bras : si un bras est masqué à une étape, l'autre l'est aussi
    # (sinon total - bras visible révélerait la valeur)
    for i in range(len(cascade[bras[0]])):
        if any(masque[b][i] for b in bras):
            for b in bras:
                masque[b][i] = True
    return {b: [f"<{seuil}" if masque[b][i] else v for i, v in enumerate(cascade[b])] for b in bras}
