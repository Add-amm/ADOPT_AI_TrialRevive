# TrialRevive : prototype d'appariement (étages 1, 2 et 4)

Une hypothèse (SEH) entre, les essais sont triés, chaque exclusion est expliquée.
L'IA propose les fiches, ce code tranche : aucun chiffre ni verdict ne vient d'une IA.

## Fichiers

| Fichier | Rôle |
|---|---|
| `data/seh_kras_2009.json` | Fiche de la question : KRAS sauvage et anti-EGFR, cancer colorectal métastatique, état du monde figé au 1er janvier 2009 |
| `data/fiches_essais_fictives.json` | 8 fiches fictives, une par cas de figure (retenu, toléré, exclu pour chaque raison) |
| `matcher.py` | Moteur : étage 1 (obligatoires), étage 2 (tolérances, deux bras, puissance a priori), étage 4 (R, E, G) |
| `source_postgres.py` | Lecture seule du corpus PostgreSQL, connexion et TLS vérifiés, sans secret dans le code |
| `adaptateur_base.py` | Conversion de la colonne JSON standardisée en fiches, depuis PostgreSQL par défaut ou depuis un export explicite |
| `.env.example` | Paramètres non secrets et noms des variables à renseigner localement |
| `requirements.txt` | Dépendances propres à ce dossier |
| `stats.py` | Puissance de l'interaction, exigence en événements, Schoenfeld, masquage, différences standardisées |
| `fetch_ctgov.py` | Récupère les vrais essais sur ClinicalTrials.gov (à lancer sur un poste avec internet) |
| `test_trialrevive.py` | Tests, dont les chiffres de l'exemple de la description technique (199 événements, 58 %, 85 %) |

## Lancer

Depuis ce dossier (`cd nouvel_essai_stat`), avec l'environnement virtuel activé :

```bash
python -m pip install -r requirements.txt
```

### PostgreSQL : source par défaut

Renseigner **`DATABASE_URL`** avec le connecteur communiqué, dans une variable d'environnement ou dans `nouvel_essai_stat/.env`. Pour créer ce fichier s'il n'existe pas encore, partir de `.env.example`. Ne pas écraser une configuration existante. Le fichier `.env` est ignoré par Git ; ne jamais publier la valeur du connecteur contenant le mot de passe.

On peut aussi laisser `DATABASE_URL` vide et renseigner uniquement **`PGPASSWORD`**. Les paramètres non secrets suivants sont déjà les valeurs par défaut du connecteur :

| Paramètre | Valeur par défaut |
|-----------|-------------------|
| Hôte | `db.rnlfbeksplyoywweoddo.supabase.co` |
| Port | `5432` |
| Base | `postgres` |
| Utilisateur | `postgres` |
| Schéma / table / colonne | `trialstd.trials.json` |

La table et la colonne sont le **schéma attendu d'après l'adaptateur existant**, pas une découverte de la base distante. Les variables `PG_TRIALS_SCHEMA`, `PG_TRIALS_TABLE` et `PG_TRIALS_JSON_COLUMN` permettent de les changer. La colonne doit contenir un objet JSON/JSONB standardisé (schéma 1.0 : `identity`, `design`, `samples`, etc.), ou un texte JSON représentant cet objet. Ce n'est pas un connecteur universel pour n'importe quel schéma relationnel.

```bash
# Sans fichier d'entrée : lire PostgreSQL, adapter les essais et apparier.
python matcher.py

# Même source PostgreSQL, avec une autre SEH, un filtre ou une sortie explicite.
python matcher.py data/seh_kras_2009.json --corpus kras --sortie outputs/resultat_kras.json

# Produire seulement les fiches standardisées, sans lancer l'appariement.
python adaptateur_base.py --corpus kras --sortie outputs/fiches_base.json
```

Le résultat par défaut est `outputs/resultat_appariement.json`, indépendant du répertoire d'appel. Aucun export de toutes les tables n'est nécessaire. Le connecteur ne lit que la colonne configurée, par lots de 500, dans une transaction **READ ONLY**, avec un délai de connexion de 10 secondes et un délai de requête de 30 secondes. TLS utilise `verify-full` : pour les domaines Supabase, la CA publique fournie dans `certs/supabase-prod-ca-2021.crt` est utilisee (la CA privee du pooler est absente de `certifi`). Les autres hotes utilisent `certifi`. Un `sslrootcert` explicite dans `DATABASE_URL` est prioritaire sur `PGSSLROOTCERT`, puis sur la CA par defaut. Le chemin de la CA incluse est independant du repertoire de lancement ; aucun telechargement au demarrage. Ne pas desactiver la verification en cas d'erreur de certificat. La provenance et le SHA-256 du certificat sont documentes dans `certs/README.md`.

Un secret manquant, une erreur de connexion ou une table/colonne inconnue arrête la commande avec un message lisible. **Aucun basculement silencieux vers les huit fiches fictives n'est effectué.** Les erreurs publiques ne contiennent ni URI, ni mot de passe, ni contenu d'une ligne. Les variables de l'environnement ont priorité sur les fichiers `.env` locaux.

### Mode fichier explicite, hors ligne

L'ancienne commande reste compatible :

```bash
python matcher.py data/seh_kras_2009.json data/fiches_essais_fictives.json outputs/resultat_demo.json
# équivalent avec choix explicite de la source :
python matcher.py data/seh_kras_2009.json data/fiches_essais_fictives.json --source fichier

# Adapter des exports de la base sans connexion PostgreSQL :
python adaptateur_base.py trials_rows.csv --sortie outputs/fiches_base.json
python adaptateur_base.py corpus.jsonl.gz --corpus kras --sortie outputs/fiches_base.json

python -m pytest -q

# vrais essais publics
python fetch_ctgov.py --sortie data/fiches_ctgov.json
# sans internet, à partir des données brutes déjà téléchargées :
python fetch_ctgov.py --depuis-brut data/ctgov_brut.json --sortie data/fiches_ctgov.json
python matcher.py data/seh_kras_2009.json data/fiches_ctgov.json
```

Les exemples fictifs restent des données de test choisies explicitement. Les interfaces HTML de ce dossier affichent un résultat JSON déjà calculé ; elles n'ouvrent jamais elles-mêmes une connexion PostgreSQL et ne doivent recevoir aucun mot de passe. Charger le résultat `outputs/resultat_appariement.json` pour afficher une analyse issue de la base. Les autres dossiers du projet, dont `src/` et le serveur web principal, ne sont pas modifiés par ce changement.

### Verification du correctif TLS

- Depuis `nouvel_essai_stat`, `python -X utf8 -m pytest -q` : **52 tests reussis**, dont 12 nouveaux cas de regression TLS. Le mode UTF-8 permet aux anciens tests de lire leurs fixtures correctement sous Windows.
- Connexion authentifiee au pooler Supabase avec la CA incluse et `sslmode=verify-full` : **reussie**. TLS actif, transaction en lecture seule et `SELECT 1` verifies.
- Test negatif avec le bundle `certifi` seul : certificat rejete, sans repli TLS non verifie.
- Le schema confirme est `trialstd` : lecture de `trialstd.trials.json` et conversion par l'adaptateur verifiees, sans export du corpus.
- Aucun secret ni fichier `.env` modifie. Aucun contenu de ligne affiche ou exporte.

Les essais du registre passent l'étage 1 puis tombent dans « à compléter » : le registre
ne donne ni les prélèvements, ni la couverture, ni le taux d'événements, ni le consentement.
On remplit ces champs (`prelevements`, `taux_collecte_prevu`, `taux_evenements_prevu`,
`consentement_portee`) à la main ou par lecture IA, avec la source dans `sources`.

## À vérifier ou à décider

- Les effets attendus de la SEH (HR 0,45 et 0,99, prévalence de KRAS sauvage 57 %) sont repris de mémoire d'Amado 2008 : à relire dans l'article.
- `PLAFOND_EXTERNE = "E3"` : plafond des essais externes, paramètre à calibrer avec l'équipe.
- Pour un critère de réponse (ORR), la puissance est calculée comme pour la survie : c'est une approximation.
- Le stade (métastatique ou non) est deviné à partir des conditions et du titre : `stade: null` signifie « à vérifier ».
- Pas encore branché : l'étage 3 (faux patients, cascade S0 à S4), le rattrapage sémantique, le contrôle de nouveauté.
