# TrialRevive : prototype d'appariement (étages 1, 2 et 4)

Une hypothèse (SEH) entre, les essais sont triés, chaque exclusion est expliquée.
L'IA propose les fiches, ce code tranche : aucun chiffre ni verdict ne vient d'une IA.

## Fichiers

| Fichier | Rôle |
|---|---|
| `data/seh_kras_2009.json` | Fiche de la question : KRAS sauvage et anti-EGFR, cancer colorectal métastatique, état du monde figé au 1er janvier 2009 |
| `data/fiches_essais_fictives.json` | 8 fiches fictives, une par cas de figure (retenu, toléré, exclu pour chaque raison) |
| `matcher.py` | Moteur : étage 1 (obligatoires), étage 2 (tolérances, deux bras, puissance a priori), étage 4 (R, E, G) |
| `stats.py` | Puissance de l'interaction, exigence en événements, Schoenfeld, masquage, différences standardisées |
| `fetch_ctgov.py` | Récupère les vrais essais sur ClinicalTrials.gov (à lancer sur un poste avec internet) |
| `test_trialrevive.py` | Tests, dont les chiffres de l'exemple de la description technique (199 événements, 58 %, 85 %) |

## Lancer

```bash
pip install scipy pytest
python matcher.py data/seh_kras_2009.json data/fiches_essais_fictives.json
python -m pytest -q

# vrais essais publics
python fetch_ctgov.py --sortie data/fiches_ctgov.json
# sans internet, à partir des données brutes déjà téléchargées :
python fetch_ctgov.py --depuis-brut data/ctgov_brut.json --sortie data/fiches_ctgov.json
python matcher.py data/seh_kras_2009.json data/fiches_ctgov.json
```

Les essais du registre passent l'étage 1 puis tombent dans « à compléter » : le registre
ne donne ni les prélèvements, ni la couverture, ni le taux d'événements, ni le consentement.
On remplit ces champs (`prelevements`, `taux_collecte_prevu`, `taux_evenements_prevu`,
`consentement_portee`) à la main ou par lecture IA, avec la source dans `sources`.

## Revue de Léo (14 nov.) : ce qui est intégré

| n° | Correction | Où |
|---|---|---|
| 1 | L'indication est aussi cherchée dans le titre et l'éligibilité ; trouvée là seulement → gardé avec avertissement | matcher, étage 1 |
| 2 | Puissance en bas et haut de fourchette, essai chevauchant 80 % gardé avec preuve plafonnée | déjà fait en v4 (le banc a testé le commit d'avant) |
| 3 | Essai enregistré mais pas commencé à la date de l'hypothèse → liste « en_cours », ni retenu ni écarté | matcher, étage 1 |
| 4 | Sang ≈ plasma ≈ sérum (familles de matériel) ; message d'échec sans « tissu tumoral » codé en dur | matcher, étage 2 |
| 5 | Essai réservé aux porteurs du marqueur → écarté, interaction non testable | matcher + adaptateur (population.biomarker_selected) |
| 6 | Égalités départagées par identifiant d'essai : classement identique quelle que soit la source | matcher, tri |
| + | Un essai présent dans plusieurs corpus est compté une fois (fiche la plus complète gardée) | matcher |
| + | Étiquette another_class_member contredite par les bras (cas PACCE) → gardé avec avertissement | matcher, étage 1 |

Reste ouvert, côté adaptateur du banc : tailles d'effet par question (la fiche de la question les porte déjà), et les essais en cours sans effectif, qui restent « à compléter ».

## À vérifier ou à décider

- Les effets attendus de la SEH (HR 0,45 et 0,99, prévalence de KRAS sauvage 57 %) sont repris de mémoire d'Amado 2008 : à relire dans l'article.
- `PLAFOND_EXTERNE = "E3"` : plafond des essais externes, paramètre à calibrer avec l'équipe.
- Pour un critère de réponse (ORR), la puissance est calculée comme pour la survie : c'est une approximation.
- Le stade (métastatique ou non) est deviné à partir des conditions et du titre : `stade: null` signifie « à vérifier ».
- Pas encore branché : l'étage 3 (faux patients, cascade S0 à S4), le rattrapage sémantique, le contrôle de nouveauté.
