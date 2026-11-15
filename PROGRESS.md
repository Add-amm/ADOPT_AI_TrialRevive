# PROGRESS — Avancement TrialRevive

Dernière mise à jour : **15 novembre 2026**, par Codex. État constaté dans l'environnement cloud.

## Tableau d'avancement

Statuts : ⬜ à faire · 🟨 partiel / validation restante · ✅ fini et vérifié dans le périmètre indiqué · ❌ bloqué · ✂️ hors prototype.

| # | Étape | Statut | Vérification et reste |
|---|-------|--------|-----------------------|
| 0 | Setup | ✅ | Python 3.12, dépendances cohérentes, serveur HTTP 200, pytest 8.4.2 (`pytest<9` déjà déclaré). |
| 1 | Essais publics | ✅ | 104 essais uniques en base depuis les JSON publics en cache ; reconstruction hors ligne vérifiée. Existence dans le cache, pas nouvelle validation en ligne. |
| 2 | CV des essais | 🟨 | 104 fiches ; six PMID/DOI recoupés avec les références du registre en cache. Effectifs KRAS, méthodes et conclusions à relire dans les articles. Extraction IA optionnelle non exécutée. |
| 3 | Fiche question | 🟨 | KRAS/panitumumab et KRAS/cetuximab acceptés, questions ambiguës et NRAS/BRAF/RAS refusés. `validee_par_humain=False` : relecture Science restante. |
| 4 | Faux patients | ✅ | 400 patients fictifs, seed 42, proportions et reproductibilité vérifiées ; CSV suivi inchangé. |
| 5 | Moteur | ✅ technique | Démo : 6 retenus / 98 écartés avec raison ; **252** patients complets. Pour cetuximab : comptage interne indéterminé, car aucun bras correspondant. Scores de tolérance et validité clinique à faire relire. |
| 6 | Dossier | 🟨 | Chiffres testés contre le moteur, liens NCT et DOI, conditions et limites explicites ; export Markdown/HTML généré. Relecture clinicien/Science restante. |
| 7 | Interface | ✅ cloud | Deux interfaces fonctionnelles, comparaison partagée ; démo sans réseau testée, démarrage + clic en **0,47 s** dans AppTest (pas une mesure du navigateur du PC de scène). Test sur ce PC restant. |
| 8 | Comparaison IA | 🟨 | Module `src/compare.py`, import/validation JSON, archivage local sans écrasement, sélection de toutes les réponses, texte intégral et examen des NCT réalisés. Aucune réponse réelle disponible : expérience et relecture des sources restantes. |
| 9 | Pitch | 🟨 | `PITCH.md` corrigé, cinq diapositives dans `docs/PRESENTATION.md`, dossier statique de secours disponible. Équipe à renseigner ; vidéo, deux répétitions chronométrées et dépôt à faire. |

## Vérifications exécutées

- `python -m src.fetch --offline` puis `python -m src.cv` : **104 essais, 104 fiches**, commandes répétables.
- `python -m pip check` : aucune dépendance incohérente.
- `python -m pytest -q` : **51 tests réussis**. Couvre les deux interfaces, toutes les pages de la démo, les questions non prises en charge, le bras interne absent, les archives de comparaison, les DOI contre le cache et l'export hors ligne.
- Démo UI et export exécutés avec les connexions réseau interdites par le test. Serveur `app_ui.py` également démarré : page Streamlit HTTP 200.
- `python -m src.demo --output-dir outputs/demo` : `dossier.md`, `dossier.html` et `chiffres.json` générés ; répertoire ignoré par Git. La page HTML est autonome, ses sources externes nécessitent Internet. **Ce n'est pas une vidéo.**
- Démo recalculée : **400 → 359 → 332 → 271 → 252** (S0 à S4), **6 retenus / 98 écartés / 104 essais**. Le précédent nombre « 306 » dans ce suivi était obsolète.
- Le CSV fictif est déjà suivi par Git et n'a pas été régénéré ; l'ancienne consigne de le committer après régénération n'est plus un reste.

## Restes nécessitant une personne ou des entrées réelles

1. **Science :** suivre `docs/REVUE_SCIENTIFIQUE.md` pour les six articles, leurs effectifs KRAS et les conclusions. Lire aussi au moins trois fiches contre les sources. Garder `verifie=False` tant que cette revue n'est pas faite.
2. **Science/statistiques :** valider la question, les scores/seuils de `src/tolerances.py`, les conditions du niveau E et le dossier. E4 est un objectif conditionnel, pas une preuve clinique acquise.
3. **Comparaison :** collecter des réponses réelles avec modèle, date, question exacte, outils et données fournis ; protocole dans `data/baseline/LISEZ_MOI.md`. Vérifier au moins trois sources citées, puis étendre à 5–10 questions prises en charge. Ne pas annoncer de supériorité avant mesure.
4. **Présentation :** renseigner l'équipe, tester hors wifi sur le PC de scène, enregistrer une vidéo, copier le dossier de secours, répéter deux fois et noter les durées dans `PITCH.md`.
5. **Dépôt :** confirmer l'échéance et les règles de l'organisation, les accords et l'autorisation de publication ; déposer les livrables. Aucune de ces actions n'est attestée ici.
6. **Optionnel :** l'extraction Claude exige une clé configurée de façon sécurisée et l'accès API. Aucun secret n'a été demandé ou ajouté et aucun appel payant n'a été effectué.

## Blocages et limites constatés

- Le service bibliographique Europe PMC (`www.ebi.ac.uk`) a renvoyé **403 au niveau du proxy**. Les textes et résumés n'ont pas pu être lus par cette voie ; seuls les rattachements bibliographiques dans le cache sont vérifiés. Aucun effectif manquant n'a été inventé.
- Pas de réponse brute d'IA généraliste fournie ou présente dans `data/baseline/`. Les exemples des tests ne sont pas des mesures de performance et ne sont pas archivés comme tels.
- Les données et règles portent sur KRAS. Les champs NRAS/BRAF/RAS ne sont pas disponibles et ne réutilisent plus silencieusement les données KRAS.
- Historique Windows : erreur SSL et incompatibilité pytest 9 signalées auparavant ; sans échec reproduit dans le cloud actuel. Les vérifications TLS n'ont pas été désactivées.

## Hors prototype (non réalisés)

Veille automatique de littérature et notifications push, horloge commune des dates, normalisation par vocabulaires médicaux, index internes/externes séparés, méta-analyse et architecture pour vraies données hospitalières. Ces évolutions restent hors du plan de démonstration actuel.

## Conformité et logistique à confirmer par l'équipe avant dépôt

- [x] Démo préparée uniquement à partir des JSON publics et des patients marqués fictifs.
- [ ] Confirmer les accords de l'équipe et l'autorisation de dépôt/publication.
- [ ] Confirmer qu'aucun document confidentiel n'a été transmis à un service externe par les participants.
- [ ] Vérifier les réglages de confidentialité des outils IA utilisés par l'équipe.
- [ ] Tester le PC de scène, son autonomie, l'adaptateur et la copie de secours.

## Journal du 14 novembre 2026

- Installation et interface initiales déjà préparées, puis restaurées depuis l'environnement publié.
- Complété l'outillage de l'étape 8, sans fabriquer de réponses ni de notes comparatives.
- Préparé le dossier de revue des six articles, les liens DOI et les limites de la validation.
- Corrigé les résultats trompeurs sur les marqueurs non disponibles et sur un traitement absent de l'essai interne.
- Préparé les cinq diapositives, le pitch à jour et l'export de secours ; contrôles automatiques ci-dessus. Restes humains conservés ouverts.

## Front relié au dossier Backend (14 novembre 2026)

- Front de CBUM05-dev, branche `nouveau-front`, révision `efd42e7` intégré avec Manrope, logos et charte du coéquipier.
- Appel du vrai `Backend/matcher.py` par un adaptateur de présentation extérieur au dossier ; les 19 fichiers Backend suivis restent identiques.
- Classements internes/externes, exclusions, fiches à compléter et essais en cours conservés ; pas de verdict global ni de patients S4 inventés.
- PostgreSQL par défaut ; mode fichier fictif uniquement sur choix explicite. Connexion distante non validée dans le cloud.
- 91 tests du site réussis ; 52 tests Backend existants réussis avant intégration. Parcours Chromium et téléchargement du dossier validés, sans ressource distante.
- Site de démonstration démarré sur le port 8766 ; détails et commandes dans `docs/INTEGRATION_FRONT.md`.

## Campagne de tests globale après intégration du front

- **161 tests réussis, aucun échec ni test ignoré** : 93 dans `tests/`, 52 dans `Backend/` et 16 dans `trialrevive/`, exécutés séparément.
- Parcours Chromium validés sur ordinateur (1440 px), tablette (820 px) et mobile (390 px), sur les neuf onglets jusqu'au téléchargement du dossier ; corpus vide et corpus de 500 fiches fictives également vérifiés. Aucune erreur JavaScript ni requête distante pendant ces parcours.
- Défaut corrigé dans `web/css/app.css` : le dernier onglet sortait de l'écran sur mobile. La barre inférieure peut maintenant défiler horizontalement. Deux tests de régression couvrent les neuf onglets à 390 et 820 px.
- Dépendances (`pip check`) et syntaxe JavaScript contrôlées. Les 19 fichiers Backend suivis restent identiques, empreintes SHA-256 vérifiées.
- Connexion PostgreSQL réelle non testée : identifiants absents de l'environnement et résolution DNS des hôtes Supabase en échec. L'absence de configuration renvoie HTTP 503 sans données fictives de remplacement.
- Rapport, captures et résultats XML disponibles dans `outputs/verification/` (ignoré par Git). Correction mobile, tests et documentation conservés localement ; aucun push pendant cette campagne.

## Suppression des cercles — 15 novembre 2026

- Retrait complet de la grille de cercles de l'aperçu, de sa légende et de son code associé. Total des essais, répartition par statut et accès aux fiches dans les onglets conservés.
- Huit tests navigateur/charte réussis et syntaxe JavaScript valide. Six parcours avec réponses API fictives de 0, 8 et 19 364 essais sur ordinateur et mobile confirment que la hauteur de l'aperçu ne dépend plus du nombre d'essais ; aucune erreur JavaScript ni requête distante.
- Changements limités au front et à la documentation. Les 19 fichiers Backend suivis restent identiques par SHA-256. Captures et mesures dans `outputs/verification/sans-cercles/` ; aucun push effectué.

## Aperçu des résultats allégé — 15 novembre 2026

- Retrait des cartes répétitives « Par essai » et du bloc des données patients non calculées de l'aperçu. Question, trois compteurs, trois fiches retenues au maximum et accès au dossier conservés ; détails et sources toujours accessibles.
- Liens vers les fiches à compléter et les essais en cours affichés lorsque ces statuts sont présents. L'aperçu conserve l'ordre des essais reçu et donne accès aux listes complètes.
- Huit tests navigateur/charte réussis ; huit parcours fictifs couvrent les corpus vide, de démonstration, avec statuts supplémentaires et de 19 364 essais. Affichage final vérifié de 320 à 1440 pixels, sans débordement, y compris pour le compteur 190 000 sur petit écran.
- Backend et API inchangés. Captures et résultats dans `outputs/verification/resultats-epures/`. Branche de livraison : `integration/front-backend-matcher`.
