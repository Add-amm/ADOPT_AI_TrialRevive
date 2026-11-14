# Intégration du nouveau front au backend local

## Périmètre et provenance

- Branche de travail : `integration/nouveau-front-api`, créée depuis `ac24d3f` dans **Add-amm/ADOPT_AI_TrialRevive**.
- Source du front : **CBUM05-dev/ADOPT_AI_TrialRevive**, branche `nouveau-front`, commit `f8676d432d94835a539683c0e38f5eb669842952`.
- Clone d'inspection séparé : `/tmp/trialrevive-front.XGPsjt/repo`. Il est temporaire ; aucune dépendance d'exécution ne pointe vers ce chemin.
- Copiés sans modification : **tout `web/`**, `docs/GUIDE_FRONT.md`, `docs/CONTRAT_API.md` (13 fichiers au total, vérifiés octet par octet).
- Aucun merge, aucun import de l'historique distant, aucun remote ajouté au dépôt local. Le `server.py` de référence a seulement été lu ; le serveur local a été écrit pour appeler les modules locaux.
- Aucun fichier préexistant n'est modifié : `src/`, interfaces Streamlit, exigences d'origine, tests antérieurs et données suivies sont conservés. Le push se fait sur cette branche distincte de `main`, uniquement sur demande explicite de l’utilisateur.

Le contrat était absent du premier commit cloné (`5364ae0`). Le commit `f8676d4`, publié pendant l'inspection, a ajouté uniquement ce document ; il a ensuite été récupéré dans le clone temporaire et copié.

## Écarts constatés avant écriture

| Attendu du front / contrat | Backend existant | Ajout d'intégration |
|---------------------------|------------------|---------------------|
| Site `/` et ressources `/assets/` | Deux interfaces Streamlit, aucun serveur JSON | Nouveau `server.py` Starlette, fichiers statiques locaux |
| Informations et analyse JSON | Fonctions dans `src/question.py`, `src/engine.py`, `src/dossier.py` | Routes appelant le pipeline local inchangé |
| Format du dossier | Les champs attendus sont déjà calculés | `web_adapter.py` complète la structure sans recalcul métier, convertit numpy/NaN en JSON strict |
| Téléchargement Markdown | `dossier.to_markdown` existe | Route dédiée, avec `Content-Disposition: attachment` |
| Réponses IA et comparaison | Fonctions dans `src/compare.py`, pas de routes | Exposition HTTP et validation des entrées du contrat |
| Cinq marches d'entonnoir | Quatre lorsque le comptage est indéterminé | Les quatre marches réelles sont conservées ; le front sait les afficher. Aucune valeur S4 inventée |

## Ce qui est branché

| Méthode et route | Fonction locale appelée / rôle |
|------------------|--------------------------------|
| `GET /` | `web/index.html` |
| `GET /assets/...` | CSS, JS, polices et three.js du dossier `web/`, chemins confinés |
| `GET /api/info` | `question.CAS_VEDETTE_TEXTE` |
| `POST /api/analyze` | `web_adapter.analyze` → question, chargement des CV, tri, comptage, groupes, dossier |
| `GET /api/dossier.md?question=...` | Même pipeline, Markdown généré par `src/dossier.py` |
| `GET /api/baselines` | `compare.load_baselines`, erreurs signalées, aucune archive existante réécrite |
| `POST /api/baselines/validate` | `compare.parse_record` et validation HTTP du champ facultatif `contexte` |
| `POST /api/baselines/archive` | `compare.archive_record`, nom calculé côté backend, pas de chemin fourni par le client |
| `POST /api/compare` | `compare.comparison_rows`, `same_question`, `audit_nct_references` |

Les erreurs HTTP renvoient `{"error": "message lisible"}`. La question est limitée à 600 caractères et le corps à 2 Mo, vérifié pendant sa lecture. Les erreurs métier de saisie sont 400, le dépassement de taille 413, une indisponibilité interne 503. Les détails internes ne sont pas exposés au client.

L'adaptateur ne change pas les niveaux R/E/G, les scores, l'ordre des essais ou les calculs. Un champ absent devient `null`, `[]`, `{}` ou « non calculé » selon sa structure ; une validation absente n'est jamais remplacée par `true`. Aucun nombre ou lien scientifique n'est fabriqué. Le test de comparaison au pipeline contrôle chaque valeur préexistante et le Markdown exact.

## Lancer

Depuis la racine du dépôt, avec l'environnement virtuel activé :

```bash
python -m pip install -r requirements-web.txt
python server.py 8765
```

Le serveur écoute sur `127.0.0.1`, port 8765 dans la vérification cloud. Le port est librement configurable ; `python server.py` utilise 8000 par défaut. Le site utilise la même origine pour son API : aucun réglage de CORS ou de serveur frontal distinct n'est nécessaire. Les interfaces Streamlit restent utilisables séparément.

La base existante est réutilisée. Si elle manque dans une nouvelle installation, la reconstruire explicitement avec les données publiques en cache :

```bash
python -m src.fetch --offline
python -m src.cv
```

L'API ne lance pas ces commandes automatiquement, ne télécharge aucun essai et ne déclenche aucun appel IA.

Le guide copié présente les commandes et le nombre de tests du dépôt source. Pour **ce dépôt**, utiliser les compléments d'installation et les commandes ci-dessus / ci-dessous, sans remplacer `requirements.txt`.

## Tests et navigateur

```bash
python -m pip install -r requirements-web-test.txt
python -m pytest -q tests/test_web_api.py
python -m pytest -q tests/test_web_browser.py
python -m pytest -q
python -m pip check
```

Le contrôle navigateur utilise Chromium système et Playwright. Si nécessaire, installer Chromium par le mécanisme de la machine puis indiquer son exécutable avec `TRIALREVIVE_CHROMIUM`. Sans Playwright ou Chromium, ce contrôle est explicitement sauté ; il ne faut alors pas annoncer une validation navigateur. Les tests API restent exécutables sans ces outils optionnels.

Vérifications exécutées dans cet environnement :

**79 tests réussis, aucun échec ni test sauté** : 51 tests préexistants, 27 tests API/adaptateur et un parcours navigateur. `pip check` ne signale aucune dépendance incohérente.

- Routes sur un vrai serveur local : contrats d'entrée/sortie, erreurs, données du pipeline, téléchargement, archives isolées et répétables, comparaison, fichiers statiques et chemins hors du dossier refusés.
- Navigateur Chromium réel : accueil → cas de démo → aperçu → essais retenus (détail) → écartés → patients → dossier → téléchargement Markdown.
- Import puis archivage d'une **fixture de test**, affichage intégral de la réponse et conservation du balisage comme texte. Aucun script ni image provenant de la réponse n'est exécuté/chargé.
- Saisie NRAS refusée, cetuximab affiché avec comptage interne indéterminé.
- Toutes les requêtes du navigateur hors de l'origine locale ont été interdites pendant le test : **aucune ressource distante demandée**, polices et three.js servis localement, aucune erreur JavaScript non gérée.
- Démo inchangée : **104 essais, 6 retenus, 98 écartés, 252 patients fictifs complets**.
- Capture de la page Dossier : `outputs/front/dossier.png` (sortie locale ignorée par Git).

## Modifications du front

**Aucune.** Les 11 fichiers de `web/`, y compris les polices et licences, sont identiques au commit source. Le seul `innerHTML` du code applicatif sert aux SVG constants (icônes et illustrations) ; les données sont ajoutées sous forme de nœuds texte. Aucun changement d'apparence ou de mise en page n'a été effectué.

## Ce qui reste

- Les limites scientifiques et fonctionnelles du backend sont conservées : KRAS uniquement, pas de bras cetuximab interne, références et règles à relire par la personne Science, aucune comparaison de performance réelle sans réponse collectée.
- Le contrat annonce cinq marches, mais les cas indéterminés du backend en exposent quatre : écart documenté et affiché sans inventer de S4.
- Les accès GitHub de chaque membre de l'équipe se gèrent séparément. Le clone a réussi avec l'authentification de cet environnement ; cela n'atteste pas des droits d'un autre compte. Aucun collaborateur n'a été ajouté.
- Revue et éventuel push de cette branche uniquement après demande explicite de l'utilisateur.
