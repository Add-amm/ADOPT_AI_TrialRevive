# TrialRevive : prototype d'appariement (étages 1, 2 et 4)

Une hypothèse (SEH) entre, les essais sont triés, chaque exclusion est expliquée.
L'IA propose les fiches, ce code tranche : aucun chiffre ni verdict ne vient d'une IA.

## Fichiers

| Fichier | Rôle |
|---|---|
| `data/seh_kras_2009.json` | Fiche de la question : KRAS sauvage et anti-EGFR, cancer colorectal métastatique, état du monde figé au 1er janvier 2009 |
| `data/fiches_essais_fictives.json` | 8 fiches fictives, une par cas de figure (retenu, toléré, exclu pour chaque raison) |
| `matcher.py` | Moteur : étage 1 (obligatoires), étage 2 (tolérances, deux bras, puissance a priori), étage 4 (R, E, G) |
| `source_postgres.py` | Connecteur en lecture seule repris de `nouvel_essai_stat`, avec vérification TLS |
| `adaptateur_base.py` | Convertit les lignes de la base standardisée vers les fiches propres à VF_stats |
| `requirements.txt`, `.env.example`, `certs/` | Dépendances, paramètres non secrets et certificat CA public |
| `stats.py` | Puissance de l'interaction, exigence en événements, Schoenfeld, masquage, différences standardisées |
| `fetch_ctgov.py` | Récupère les vrais essais sur ClinicalTrials.gov (à lancer sur un poste avec internet) |
| `test_trialrevive.py` | Tests, dont les chiffres de l'exemple de la description technique (199 événements, 58 %, 85 %) |

## Lancer

Depuis le dossier `VF_stats`, avec votre environnement Python activé :

```bash
python -m pip install -r requirements.txt

# Entrée automatique : PostgreSQL, sans export intermédiaire.
python matcher.py

# Même mode avec filtre de corpus ou SEH et sortie explicites.
python matcher.py data/seh_kras_2009.json --corpus kras --sortie outputs/resultat_kras.json

# Mode fichier explicite : ancienne commande conservée.
python matcher.py data/seh_kras_2009.json data/fiches_essais_fictives.json
python -m pytest -q

# vrais essais publics
python fetch_ctgov.py --sortie data/fiches_ctgov.json
# sans internet, à partir des données brutes déjà téléchargées :
python fetch_ctgov.py --depuis-brut data/ctgov_brut.json --sortie data/fiches_ctgov.json
python matcher.py data/seh_kras_2009.json data/fiches_ctgov.json
```

### Configuration PostgreSQL automatique

Le point d'entrée CLI reprend celui de `nouvel_essai_stat/matcher.py` ; le moteur d'appariement de VF_stats reste celui de VF_stats, avec ses corrections de Léo.

La configuration suit cet ordre :

1. Variables déjà présentes dans le processus (`DATABASE_URL`, etc.).
2. Fichier `VF_stats/.env`, s'il existe ; **sinon**, réutilisation de `nouvel_essai_stat/.env`.
3. Fichier `.env` à la racine pour les valeurs encore absentes.

Si la connexion fonctionne déjà depuis `nouvel_essai_stat/.env`, il suffit donc de lancer `python matcher.py` dans VF_stats, sans recopier le secret. Pour une configuration différente, créer `VF_stats/.env` à partir de `.env.example` et renseigner `DATABASE_URL` localement. Ne pas écraser une configuration existante. Les `.env` sont ignorés par Git et ne doivent pas être publiés. Une URL non vide prend priorité sur les paramètres séparés `PGHOST`, `PGUSER`, etc.

Comme dans la référence actuelle, la lecture porte par défaut sur **`trialstd.trials`, colonne `json`**. Ces noms sont configurables par `PG_TRIALS_SCHEMA`, `PG_TRIALS_TABLE`, `PG_TRIALS_JSON_COLUMN`. La colonne doit contenir les objets JSON/JSONB du schéma standardisé 1.0 de l'équipe, pas des dossiers patients. Seules les données d'essais publiques ou fictives sont prévues ici.

Le connecteur lit par lots de 500, dans une transaction en lecture seule, avec un délai de connexion de 10 s et un délai de requête de 30 s. TLS reste en `verify-full` : la CA publique Supabase copiée de la référence est utilisée pour les hôtes Supabase ; les autres hôtes utilisent `certifi`. `PGSSLROOTCERT` ou le paramètre `sslrootcert` de l'URL permettent de choisir une CA explicite. Aucun téléchargement ni affaiblissement de TLS n'est effectué au démarrage.

Les paramètres non secrets par défaut restent l'hôte direct Supabase du projet, port 5432, base et utilisateur `postgres`. Pour le Session pooler, conserver l'URI complète affichée par Supabase dans `DATABASE_URL`, avec son serveur et son utilisateur spécifiques. Aucun mot de passe n'est codé en dur.

Le résultat est écrit dans **`VF_stats/outputs/resultat_appariement.json`**, quel que soit le répertoire d'appel. Les anciens arguments positionnels (`SEH fiches [résultat]`) restent disponibles ; `--source fichier` permet aussi de choisir explicitement ce mode. Une panne de PostgreSQL interrompt la commande : aucun remplacement par les fiches fictives n'est effectué.

L'entrée automatique convertit les lignes avec **l'adaptateur VF_stats**, qui conserve notamment `first_posted` et les populations sélectionnées sur un marqueur. Elle laisse les doublons au moteur VF_stats, qui garde la fiche la plus complète et conserve `n_lignes_recues`. Le choix des essais, les scores, la puissance, la liste `en_cours` et l'ordre de classement ne sont pas remplacés par les règles du dossier de référence.

### Vérification de l'intégration

Dans ce dossier : **46 tests réussis** (31 existants, 15 nouveaux). Les tests couvrent l'entrée automatique simulée, les corrections métier de VF_stats, les doublons, le mode fichier, le filtre de corpus, la priorité de configuration et le chargement de la CA publique. Les fonctions métier existantes ont également été comparées à la version Git de départ et sont identiques.

La connexion à la base distante n'a pas été validée dans le cloud : aucun identifiant n'y est configuré pour ce contrôle. Le test du chargement automatique utilise des lignes fictives, sans lire de données Supabase. Les interfaces HTML continuent d'afficher un résultat JSON exporté ; elles ne reçoivent jamais le mot de passe.

Les essais du registre passent l'étage 1 puis tombent dans « à compléter » : le registre
ne donne ni les prélèvements, ni la couverture, ni le taux d'événements, ni le consentement.
On remplit ces champs (`prelevements`, `taux_collecte_prevu`, `taux_evenements_prevu`,
`consentement_portee`) à la main ou par lecture IA, avec la source dans `sources`.

## Critère de cible moléculaire (remarque de la chirurgienne, 14 nov.)

La fiche de la question porte une contrainte obligatoire `cible` (EGFR pour le cas KRAS). L'étage 1
juge d'abord la cible de la molécule (`cibles` dans la fiche d'essai, remplie depuis `interventions[].targets`
de la base et un dictionnaire de molécules connues) ; la classe de médicament ne sert plus que de repli
quand la cible n'est pas renseignée, avec un avertissement. Une molécule de même cible mais d'un autre
mécanisme (géfitinib, erlotinib) est tolérée : score 0,4 et plafond E2, valeurs à valider avec la biologiste.

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
