# TrialRevive

## Site web relié au dossier Backend

Le front de `CBUM05-dev/ADOPT_AI_TrialRevive`, branche `nouveau-front` (révision `efd42e7`), appelle maintenant **`Backend/matcher.py`** via un adaptateur de présentation. Le dossier `Backend/` reste inchangé.

```bash
python -m pip install -r requirements-web.txt
python server.py 8766
```

Par défaut, le backend lit PostgreSQL avec sa configuration habituelle (`Backend/.env` ou variables d'environnement). Si la base est inaccessible, l'erreur s'affiche ; aucune donnée fictive n'est chargée automatiquement.

Pour lancer explicitement une démonstration hors ligne sur les fiches fictives fournies :

```bash
python server.py 8766 --source fichier --fiches Backend/data/fiches_essais_fictives.json
```

Le front conserve les classements internes/externes et les statuts exclus, à compléter et en cours. Les données patients et verdicts globaux absents du backend sont affichés comme non calculés. [Détails, écarts et vérifications](docs/INTEGRATION_FRONT.md).

## Anciennes interfaces Streamlit

Prototype de faisabilité sur des essais publics ClinicalTrials.gov et 400 patients **entièrement fictifs**. Cas de démonstration : panitumumab / KRAS dans le cancer colorectal. Les références et règles cliniques restent à valider par la personne Science ; la démo n'est pas un outil de décision clinique.

## Démarrage hors ligne après installation

Depuis la racine du dépôt, Python 3.11+ (3.12 vérifié) :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.fetch --offline
python -m src.cv
python -m pytest -q
python -m streamlit run app_ui.py --browser.gatherUsageStats=false
```

Sur Windows, activer avec `.venv\Scripts\Activate.ps1` dans PowerShell. L'installation nécessite le registre de paquets ; ensuite, la démo utilise les fichiers en cache, sans clé API ni accès Internet. `app.py` reste l'interface simple de secours. Éviter `src.fetch` sans `--offline` si l'on veut conserver les données brutes du dépôt.

## Livrables et derniers préparatifs

```bash
python -m src.demo --output-dir outputs/demo
```

Cette commande produit les chiffres, le dossier Markdown et une page HTML autonome à ouvrir directement depuis le disque. La page n'utilise pas de serveur ni de bibliothèque distante ; ses liens scientifiques demandent Internet. Cet export est un secours statique, pas une vidéo.

- Comparaison IA : import JSON, archivage local, choix parmi toutes les réponses et examen des NCT dans les deux interfaces. [Protocole](data/baseline/LISEZ_MOI.md).
- [Pitch](PITCH.md), [cinq diapositives](docs/PRESENTATION.md), [revue scientifique](docs/REVUE_SCIENTIFIQUE.md).
- [Avancement et restes précis](PROGRESS.md), [vérifications](VERIFICATION.md).

Ne fournir à des services externes que des données publiques ou fictives ; ne pas publier les documents confidentiels de l'équipe. Les réponses IA réellement collectées ne sont pas encore présentes et aucune supériorité comparative n'est mesurée.
