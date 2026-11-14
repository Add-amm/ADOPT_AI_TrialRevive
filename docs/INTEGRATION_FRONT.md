# Front nouveau-front relié à Backend/matcher.py

## Résultat et périmètre

Le site utilise le front de **CBUM05-dev/ADOPT_AI_TrialRevive**, branche **nouveau-front**, commit **efd42e7329df0a38f3142d2315b9b04ff2c48c96**. Il conserve son CSS, ses illustrations, sa police Manrope, ses licences et ses logos. L'ancienne 3D et les anciennes polices ne font pas partie de cette version du front.

L'intégration est développée sur `integration/front-backend-matcher`, depuis `a74e1d9` du dépôt utilisateur. Le dépôt distant a été inspecté dans un clone temporaire séparé ; aucun historique, moteur métier ou serveur de référence n'a été fusionné dans le projet.

**Aucun fichier du dossier `Backend/` n'est modifié**, ni ses règles, ni ses calculs, ni ses tests, ni ses données ou son certificat. Les 19 fichiers suivis ont été comparés par empreinte avant et après l'intégration. Les anciens modules `src/` restent également inchangés.

Les fichiers d'intégration se trouvent hors de `Backend/` :

- `frontend_matcher_worker.py` appelle réellement les fonctions du backend, avec les imports locaux isolés dans un processus Python. Il ne remplace aucune règle par celles de l'ancien `src/`.
- `frontend_matcher.py` renomme les champs pour leur présentation, conserve le résultat brut sous `resultat_backend` et produit le dossier Markdown. Il ne recalcule aucun score, niveau de preuve ou puissance.
- `server.py` sert le site et les routes JSON ; la source par défaut est PostgreSQL. Les utilitaires d'archivage des réponses IA sont conservés, sans lancer d'appel IA.

## Écarts entre les données du backend et le front d'origine

| Donnée du backend | Affichage / adaptation |
|-------------------|------------------------|
| SEH structurée, pas de traduction de texte libre | `/api/info` propose la SEH configurée. Le champ accepte son énoncé ou son identifiant ; une autre question est refusée explicitement avant tout accès à la base. |
| `internes` et `externes`, deux classements séparés | Deux tableaux séparés, ordre du backend inchangé ; aucune liste clinique commune reclassée. |
| `exclus`, avec étages 1 et 2 et raisons détaillées | Exclusions aux exigences obligatoires ou à la compatibilité/puissance ; aucune transformation en six motifs qui ne sont pas calculés par ce moteur. |
| `a_completer` et `en_cours` | Deux vues de navigation supplémentaires, distinctes des exclusions. Tous les statuts entrent dans le total d'essais examinés. |
| Verdict R/E et gains par essai | Affichés dans chaque fiche ; le résumé global indique « Par essai ». Aucun E4, R0 ou gain global n'est ajouté. |
| `couverture_prevue`, parfois une fourchette | Pourcentage ou fourchette affichée sans en choisir une borne. Puissance a priori conservée comme valeur ou fourchette. |
| `evenements_min` de l'exigence statistique | Présenté comme un total d'événements pour l'interaction, jamais comme un nombre par groupe. |
| Pas de données patients S0–S4, médianes ou événements individuels observés | `null` ou listes vides dans l'API et « Non calculé » à l'écran ; aucun ancien chiffre de 400/252 patients n'est injecté. |
| Identifiants fictifs ou absence de NCT | Identifiant d'essai affiché, sans fabriquer de NCT ni de lien. Un lien de registre n'est formé que si une fiche fournit un NCT au format attendu ; il ne constitue pas une validation de la source. |
| Sources des fiches et hypothèses | Références fournies affichées comme texte ; aucune réanalyse ou publication de l'ancien backend ajoutée. |

Le contrat d'origine est conservé dans `docs/CONTRAT_API.md`. L'adaptation suit sa règle de valeurs absentes nulles et ajoute les champs `internes`, `externes`, `a_completer`, `en_cours`, `index`, `trial_id`, `puissance_a_priori`, `gains`, `references`, `statistique.evenements_necessaires_total`, `source_donnees` et `donnees_fictives`. Les propriétés `niveau` et les verdicts globaux restent nulles lorsqu'elles ne sont pas fournies par le backend.

## Routes branchées

- `GET /` et `/assets/...` : page, scripts, CSS, logos et police locaux.
- `GET /api/info` : hypothèse configurée, source de données et propositions de questions ; aucun accès à PostgreSQL à ce stade.
- `POST /api/analyze` : `Backend.adaptateur_base.charger_fiches` puis `Backend.matcher.apparier`, ou lecture du fichier de fiches choisi explicitement au lancement. Retour du dossier adapté, du Markdown et du résultat brut.
- `GET /api/dossier.md` : téléchargement du même dossier ; analyse mise en cache 30 secondes pour éviter une deuxième lecture immédiate de la base. Une modification de la SEH, du fichier de fiches ou des `.env` surveillés invalide le cache.
- `GET /api/baselines`, `POST /api/baselines/validate`, `POST /api/baselines/archive` : lecture, validation et archivage local des réponses réelles.
- `POST /api/compare` : comparaison à la même hypothèse, sans prétendre compter des patients absents du backend. Les NCT sont recherchés dans les fiches réellement chargées, pas dans l'ancien cache des 104 essais.

## Lancer sur son ordinateur

Depuis la racine du projet, avec le bon environnement Python activé :

```powershell
python -m pip install -r requirements-web.txt
python server.py 8766
```

Ouvrir ensuite `http://localhost:8766` sur **cet ordinateur** et laisser le terminal ouvert. Le backend utilise sa configuration habituelle, notamment `Backend/.env`. Aucun mot de passe n'est transmis au navigateur ou ajouté au dépôt. Les erreurs de connexion sont affichées sans charger silencieusement une démo.

Pour une démo hors ligne, choisir explicitement les fiches fictives existantes :

```powershell
python server.py 8766 --source fichier --fiches Backend/data/fiches_essais_fictives.json
```

Une autre SEH déjà structurée peut être fournie avec `--seh chemin/SEH.json`. Le filtre `--corpus` concerne la source PostgreSQL. Le site n'invente pas de nouvelle SEH à partir d'une saisie libre.

Les processus du serveur doivent être redémarrés après modification de Python. Le code du front est revalidé à chaque rechargement. Aucun service distant n'est requis pour les polices, logos et scripts ; PostgreSQL nécessite naturellement l'accès réseau à la base.

## Vérifications exécutées

- **91 tests dans `tests/` réussis**, dont les routes, l'adaptation du vrai backend, sept tests spécifiques de liaison, le parcours Chromium et les cinq garde-fous de charte.
- **52 tests existants du dossier `Backend/` réussis**, avant l'intégration ; tous les fichiers du dossier sont restés identiques ensuite.
- Comparaison JSON entre le résultat de la commande existante `Backend/matcher.py` et celui renvoyé sous `resultat_backend` par l'API : égalité exacte.
- Les huit fiches fictives d'origine donnent **1 interne retenu, 2 externes retenus et 5 exclus**. L'exigence de la SEH est **206 événements au total**. Ce sont les sorties du backend, pas des résultats cliniques ajoutés par le front.
- Des fixtures supplémentaires, stockées uniquement dans les répertoires temporaires des tests, vérifient les statuts à compléter/en cours, les fourchettes et le choix de la fiche complète entre doublons.
- Chromium : accueil → cas de démo → essais retenus/détail → exclus → à compléter → en cours → patients non calculés → dossier et téléchargement Markdown → import/archivage d'une réponse de test → guide.
- Aucun chargement distant ni erreur JavaScript pendant ce parcours. Le balisage d'une réponse IA importée reste du texte.
- Le site a également été démarré sur le port **8766** avec les huit fiches fictives d'origine et son rendu a été inspecté. Captures locales ignorées par Git dans `outputs/front-backend/`.
- **Connexion PostgreSQL authentifiée non vérifiée dans le cloud** : aucune configuration secrète n'y a été ajoutée. Les vérifications de lecture utilisent les fiches fictives explicites ; la source de production demeure PostgreSQL.

## Changements du front par rapport à la branche source

Seuls `web/js/app.js` et `web/index.html` ont été adaptés au format des données : hypothèse proposée par l'API, source affichée, identifiants non NCT, classements internes/externes, deux nouveaux statuts, valeurs non calculées et unités statistiques correctes. La comparaison, les détails et le téléchargement sont reliés à ces résultats. L'affichage des données reste construit avec des nœuds texte ; `innerHTML` est réservé aux constantes SVG du front.

**Aucune modification de `web/css/app.css`, `web/js/illustration.js`, des logos ou de Manrope par rapport au commit source.** Le test de charte fourni par le coéquipier est conservé et passe.

Les limites métier du backend restent celles qu'il annonce : pas de comptage individuel ni de verdict global, hypothèse en brouillon et paramètres/sources à valider par l'équipe Science. Aucune connexion ou publication GitHub supplémentaire n'est annoncée comme effectuée sans vérification.
