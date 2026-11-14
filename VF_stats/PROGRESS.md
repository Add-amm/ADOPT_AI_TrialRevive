# Avancement — entrée PostgreSQL de VF_stats

- Référence utilisée : `nouvel_essai_stat/matcher.py`.
- `python matcher.py` charge PostgreSQL par défaut, sans fichier ni export intermédiaire.
- Conversion par l'adaptateur VF_stats ; les 14 fonctions métier du matcher et les deux fonctions métier de l'adaptateur restent identiques.
- Doublons laissés au moteur VF_stats pour préserver le choix de la fiche la plus complète.
- Configurations : variables du processus, puis `.env` VF_stats ou celui de référence, puis `.env` racine.
- Lecture seule et TLS vérifié ; certificat public de référence conservé, aucun secret copié dans le dépôt.
- 46 tests réussis : 31 existants et 15 nouveaux. Ancienne commande fichier et résultats métier vérifiés.
- Connexion distante non validée ici ; les nouveaux tests utilisent exclusivement des lignes fictives.
- Développement local sur `feature/vf-stats-postgresql` ; pas de modification du dossier de référence ni de `main`.

## Critère de cible moléculaire (14 nov., soir)
- Contrainte obligatoire `cible: EGFR` dans la fiche de la question ; étage 1 juge d'abord la cible, la classe devient le repli (avertissement si cible non renseignée).
- Champ `cibles` ajouté aux fiches par les deux adaptateurs (`interventions[].targets` + molécules connues).
- TKI anti-EGFR (géfitinib, erlotinib) tolérés : score 0,4, plafond E2 — valeurs à faire valider (biologiste / chirurgienne).
- 49 tests réussis : 46 existants et 3 nouveaux. Aucun changement sur la démo fictive ni sur l'entrée PostgreSQL.
