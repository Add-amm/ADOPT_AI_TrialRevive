# Front nouveau-front relié à Backend/matcher.py

## Résultat et périmètre

Le site utilise le front de **CBUM05-dev/ADOPT_AI_TrialRevive**, branche **nouveau-front**, commit **efd42e7329df0a38f3142d2315b9b04ff2c48c96**. Il conserve sa charte, ses illustrations, sa police Manrope, ses licences et ses logos. Les ajustements d'affichage sont détaillés ci-dessous. L'ancienne 3D et les anciennes polices ne font pas partie de cette version du front.

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

- L'intégration initiale a passé **91 tests dans `tests/`**, dont les routes, l'adaptation du vrai backend, sept tests spécifiques de liaison, le parcours Chromium et les cinq garde-fous de charte. La campagne complémentaire et ses résultats sont décrits ci-dessous.
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

**Illustrations, logos et Manrope sont identiques au commit source.** Les changements CSS concernent la correction mobile, le retrait des styles des cercles et l'allègement de l'aperçu décrits ci-dessous. Le test de charte fourni par le coéquipier est conservé et passe.

Les limites métier du backend restent celles qu'il annonce : pas de comptage individuel ni de verdict global, hypothèse en brouillon et paramètres/sources à valider par l'équipe Science. Aucune connexion ou publication GitHub supplémentaire n'est annoncée comme effectuée sans vérification.

## Contrôle complémentaire du front

Le parcours à 390 pixels de large a révélé que le neuvième onglet (« Comment ça marche ») dépassait de la barre inférieure et ne pouvait pas être cliqué. La barre de navigation sous 1020 pixels est maintenant défilable horizontalement, avec une largeur minimale de 76 pixels par onglet. Aucun changement de couleur, de police, de logo ou du backend n'a été apporté.

Deux tests Chromium de régression, à 390 et 820 pixels, parcourent les neuf onglets, vérifient leur visibilité après navigation et contrôlent l'absence de débordement horizontal de la page. Le rapport de la campagne complète est généré dans `outputs/verification/` (répertoire ignoré par Git).

La campagne complète passe sans échec ni test ignoré : **93 tests dans `tests/`**, **52 dans `Backend/`** et **16 dans `trialrevive/`**, exécutés séparément pour éviter les collisions de noms de modules. Les parcours navigateur sur ordinateur, tablette et mobile, ainsi que les corpus vide et de 500 fiches fictives, aboutissent tous au dossier téléchargeable, sans erreur JavaScript ni requête distante.

La connexion PostgreSQL réelle reste non validée : cet environnement ne dispose pas des identifiants et la résolution DNS des deux hôtes Supabase échoue. Le cas sans configuration renvoie bien HTTP 503, sans repli vers la démo. Les 19 fichiers suivis de `Backend/` sont toujours identiques à leur empreinte avant intégration.

## Suppression des cercles (15 novembre 2026)

À la demande de l'utilisateur, l'aperçu ne dessine plus un cercle par essai. Le total et la répartition des statuts restent dans l'en-tête ; les tableaux et les détails des essais restent dans leurs onglets. Aucun essai ni résultat n'est retiré des données.

- `web/js/app.js` : retrait de la grille, de sa légende, des infobulles et de leur animation ; l'aperçu ne génère plus de nœud par essai.
- `web/css/app.css` : suppression des styles propres à cette grille et aux infobulles.
- `web/index.html` : suppression du conteneur d'infobulle devenu inutile.

Les huit tests du navigateur et de la charte passent, ainsi que le contrôle de syntaxe JavaScript. Six parcours supplémentaires utilisent des réponses API fictives de 0, 8 et 19 364 essais sur ordinateur et mobile : l'aperçu conserve 73 éléments DOM et la même hauteur pour chaque taille de corpus à fenêtre identique, sans erreur JavaScript ni requête distante. L'ouverture d'une fiche depuis le tableau des essais retenus fonctionne toujours. Captures et mesures : `outputs/verification/sans-cercles/` (ignoré par Git). Le backend reste inchangé ; aucune connexion PostgreSQL réelle n'est impliquée dans ces contrôles.

## Aperçu des résultats allégé (15 novembre 2026)

La page de résultats conserve la question, trois compteurs (examinés, retenus et écartés), un aperçu de trois essais retenus au maximum et les actions d'ouverture et de téléchargement du dossier. Chaque fiche affiche son titre, son identifiant, son origine interne/externe et son niveau de preuve lorsqu'il est fourni. L'ordre des essais reçu est conservé ; « Tout voir » donne accès aux classements complets.

Les trois cartes répétitives « Par essai » et le bloc des données patients non calculées ont été retirés de l'aperçu. Les conditions, sources, limites et informations patients restent accessibles dans les fiches, le dossier et les onglets correspondants. Les liens « À compléter » et « En cours » n'occupent la synthèse que si leurs effectifs sont non nuls. Un résultat sans essai retenu est indiqué explicitement.

- `web/js/app.js` : remplacement des blocs de l'aperçu par cette synthèse ; les données et routes API restent identiques.
- `web/css/app.css` : compteurs, liste courte et actions adaptés aux différentes tailles d'écran ; correction du débordement du formulaire de recherche à 320 pixels.
- `tests/test_web_browser.py` : vérification du total dans son nouveau compteur.

Vérification : **8 tests navigateur/charte réussis**, syntaxe JavaScript valide et huit parcours sur ordinateur/mobile avec des réponses fictives de 0, 8, 11 et 19 364 essais. Fiches ouvertes au clavier, statuts à compléter/en cours, liste complète, dossier et téléchargement fonctionnent ; aucune erreur JavaScript ni requête distante pendant ces parcours. Les ajustements visuels finaux ont aussi été contrôlés à 320, 390, 820 et 1440 pixels, avec des compteurs alignés et sans débordement, y compris l'affichage de 190 000 sur petit écran. Captures et mesures : `outputs/verification/resultats-epures/` (ignoré par Git). Backend inchangé.
