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
| `trialstd_adapter.py` | Fait tourner le moteur, sans le modifier, sur les données standardisées trialstd (Supabase, SQLite ou banc d'essai) |
| `test_trialstd_adapter.py` | Tests de l'adaptateur, sur des essais fabriqués |

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

## Données standardisées (trialstd)

`trialstd_adapter.py` traduit une hypothèse standardisée (schéma trialstd 1.0) en SEH et chaque essai standardisé en
fiche, appelle `matcher.apparier()` tel quel, puis rend un classement unique : retenus par le moteur, puis essais en
cours et fiches à compléter, puis exclus à l'étage 2, puis exclus à l'étage 1. Chaque essai garde la raison du moteur,
les valeurs par défaut utilisées et des citations exactes du registre. Les mêmes données sont sur Supabase (projet
« Trial Survive », schéma `trialstd`), dans `trialstd.sqlite` et dans les fichiers du banc d'essai.

```bash
python trialstd_adapter.py test_sami_Q001 --sqlite chemin/vers/trialstd.sqlite
TRIALSTD_PG_DSN=postgresql://... python trialstd_adapter.py test_sami_Q001 --supabase   # psycopg requis
python trialstd_adapter.py dev_sami_H1 --banc chemin/vers/bench/standardized --sortie resultat.json
```

Ce que ni l'hypothèse ni le registre ne donnent est rempli par `DEFAUTS` et écrit dans la raison de l'essai : HR 0,5
chez les X+ et 1,0 chez les X- (les valeurs d'Amado 2008 de la SEH KRAS sont postérieures à 2007 et ne sont pas
reprises), prévalence 0,4 si l'hypothèse n'en donne pas, couverture prévue 0,9 si le prélèvement est exigé à
l'inclusion et 0,8 sinon, taux d'événements 0,75 en situation avancée et 0,30 en situation précoce. Pendant l'appel au
moteur, `effectif_randomise` et `criteres` comptent parmi les champs « à compléter » : le registre ne donne pas
l'effectif des essais en cours à la date de coupure.

Sur l'exemple KRAS de Sami (32 essais, coupure au 1er mai 2007), les 13 premiers sont les 13 essais randomisés
anti-EGFR du cancer colorectal métastatique ; sur les 9 cas de développement du banc d'essai, MRR 0,84.

## À vérifier ou à décider

- Les effets attendus de la SEH (HR 0,45 et 0,99, prévalence de KRAS sauvage 57 %) sont repris de mémoire d'Amado 2008 : à relire dans l'article.
- `PLAFOND_EXTERNE = "E3"` : plafond des essais externes, paramètre à calibrer avec l'équipe.
- Pour un critère de réponse (ORR), la puissance est calculée comme pour la survie : c'est une approximation.
- Le stade (métastatique ou non) est deviné à partir des conditions et du titre : `stade: null` signifie « à vérifier ».
- Pas encore branché : l'étage 3 (faux patients, cascade S0 à S4), le rattrapage sémantique, le contrôle de nouveauté.
