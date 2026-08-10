# HA Doctor 0.9.0 — Documentation technique

## Objectif

HA Doctor effectue un diagnostic local et en lecture seule d'une installation Home Assistant. La 0.9 conserve le moteur technique accumulé depuis la 0.7 et ajoute une couche de triage destinée à transformer un rapport complexe en décisions ordonnées.

Aucune fonction 0.9 ne corrige, ne supprime, ne désactive ou ne redémarre Home Assistant.

## Chaîne d'analyse 0.9

1. collecte Home Assistant / Supervisor ;
2. snapshot éphémère unique des états ;
3. analyse YAML autorisée, packages et blueprints ;
4. règles déterministes ;
5. santé `unavailable` / `unknown` ;
6. Entity Registry / Device Registry par WebSocket ;
7. corrélation intégration / appareil / cluster ;
8. Entity Flow V3.1 ;
9. architecture et blast radius ;
10. Controller Semantics V6 ;
11. Resilience V4 ;
12. Entity Lineage + Registry Blast Radius V4 ;
13. temporalité V3.1 ;
14. Score V4 + Preview V5 ;
15. Product Triage V1 ;
16. Diagnostic Trust V1 ;
17. Report Self-Check V1 ;
18. exports et interface.

Les étapes 15 à 17 travaillent exclusivement sur le rapport déjà construit : **0 lecture d'état Home Assistant supplémentaire**.

## Données lues

- API Home Assistant : configuration générale, états courants et services nécessaires au scanner ;
- API Supervisor : informations système accessibles au rôle configuré ;
- WebSocket Home Assistant via Supervisor : registres d'entités et d'appareils ;
- `/ha_config` monté en lecture seule : fichiers YAML autorisés.

## Données exclues

- `secrets.yaml` / `secrets.yml` ;
- `.storage` en lecture fichier directe ;
- bases SQLite ;
- clés et certificats ;
- sauvegardes binaires ;
- valeurs de secrets ;
- token Supervisor dans le rapport ;
- états bruts dans l'historique ;
- YAML brut dans l'historique.

## Doctor View V1

Bloc : `doctor_view`.

Champs principaux :

- `verdict` ;
- `technical_health_score` ;
- `score_v5_preview` ;
- `projected_after_top_3` ;
- `next_action` ;
- `next_best_actions` ;
- `triage_counts` ;
- `trust` ;
- `noise_reduction` ;
- `change_digest` ;
- `projection`.

Le verdict est une présentation produit. Il ne remplace pas le score technique.

## Triage Board V1

Bloc : `triage_board`.

Le moteur normalise chaque action et calcule :

- lane client ;
- risque 0–100 ;
- confiance A/B/C/D ;
- type de traitement ;
- effort ;
- gain de score connu ;
- impact de dépendance ;
- nombre d'automatisations impactées.

### Lanes

- `fix_now` : correction prioritaire ;
- `investigate` : vérification à impact moyen/fort ;
- `review` : revue à plus faible sévérité ;
- `optimize` : maintenance/optimisation ;
- `watch` : observation.

Le classement n'exécute aucune action.

## Diagnostic Trust V1

Bloc : `diagnostic_trust`.

Le score de confiance du scan est séparé du score de santé de Home Assistant. Il est dégradé lorsque le moteur rencontre notamment :

- quality gate en échec ;
- incohérence interne ;
- faible confiance de flow ;
- erreurs de lineage ;
- cibles dynamiques non résolues.

Ce mécanisme évite de présenter un rapport incomplet avec la même assurance qu'un rapport entièrement validé.

## Report Self-Check V1

Bloc : `self_check`.

L'auto-contrôle vérifie notamment :

- version et schéma ;
- scores 0–100 ;
- compteurs findings/sévérités ;
- unicité des IDs ;
- cohérence `action_plan.total` et `counts` ;
- cohérence `diagnostic_summary` ;
- identité des paires de contrôleurs ;
- compteurs Resilience V4 ;
- bornes des taux de Flow ;
- compteurs temporels ;
- invariants de confidentialité ;
- absence de lecture d'état ajoutée par la couche 0.9 ;
- sérialisation JSON ;
- absence de NUL ;
- taille locale raisonnable.

Un `self_check.status=fail` indique que le rapport doit être considéré comme techniquement incohérent, même si certaines conclusions individuelles paraissent plausibles.

## Entity Flow V3.1

Le graphe différencie :

- triggers ;
- contrôles ;
- appels ;
- lectures ;
- cibles dynamiques et confiance.

Les templates Jinja ne sont jamais exécutés. Les cibles non démontrables restent explicitement incertaines.

## Controller Semantics V6

V6 combine les preuves des générations précédentes :

- états mutuellement exclusifs ;
- temps fixes exclusifs ;
- commandes déterministes équivalentes ;
- réconciliation de démarrage ;
- handoffs par helper ;
- conditions `states(entity) in [...]` littérales ;
- interlock correctif direct ;
- interlock médié.

Une preuve ne supprime une paire de la revue que si les chemins de commandes opposées sont couverts par une logique statique suffisante.

## Resilience V4

Les dépendances critiques sont séparées selon leur rôle opérationnel :

- contrôle physique ;
- contrôle helper ;
- observation ;
- autre contrôle.

Seuls les consommateurs physiques pertinents alimentent le risque SPOF externe. V4 reconnaît aussi certains comportements fail-safe : `numeric_state`, variable de validité, branche de repli explicite.

## Entity Lineage et Blast Radius

Le lineage relie :

`source -> entité dérivée -> automatisation`

Les arêtes suffisamment sûres peuvent enrichir le blast radius d'une panne registry. Les sorties seulement supposées par nom ne sont pas utilisées comme preuve forte tant qu'elles ne sont pas confirmées dans le graphe effectif.

## Temporal V3.1

Historique compact limité à 20 snapshots. Il conserve des IDs, compteurs, scores et timestamps, sans états bruts.

La persistance nécessite des observations séparées dans le temps. Une disparition du plan mais pas du diagnostic est classée comme déclassement, pas comme résolution réelle.

## Scores

### Score V4

Reste le score technique primaire pour préserver la continuité de l'historique.

### Score V5 Preview

Reste non destructif (`applied_to_primary_score=false`). Il sert à tester une future migration et à produire des scénarios de gain après correction.

La couche produit 0.9 ne modifie aucun des deux calculs en amont.

## Exports

### Share V3

Schéma : `ha-doctor-share/3`.

- modèle : `assistant_share_report_v3` ;
- cible : 28 Ko ;
- plafond dur : 32 Ko ;
- conservation des IDs de findings/actions ;
- suppression progressive des sections secondaires en cas de dépassement ;
- aucun état brut, YAML brut ou secret.

### Markdown support

`build_markdown_summary()` génère un résumé destiné à être lu directement : verdict, scores, priorités, actions, évolution, self-check et confidentialité.

## API 0.9

Endpoints hérités :

- `/api/status`
- `/api/report`
- `/api/summary`
- `/api/insights`
- `/api/actions`
- `/api/architecture`
- `/api/quality`
- `/api/flow`
- `/api/coverage`
- `/api/history`
- `/api/control-intelligence`
- `/api/diagnostic?id=...`
- `/health`

Endpoints 0.9 :

- `/api/version`
- `/api/doctor-view`
- `/api/self-check`
- `/api/share-report`
- `/api/download-share`
- `/api/download-support-summary`

Aucun endpoint d'écriture Home Assistant n'est introduit.

## Packaging et CI

Le Dockerfile conserve `COPY *.py ./`.

La CI 0.9 vérifie :

- tous les tests historiques ;
- tests 0.9 ;
- `py_compile` de tous les modules ;
- syntaxe JavaScript de toutes les couches UI ;
- cohérence de version ;
- build Docker réel ;
- présence et import des modules ;
- endpoints HTTP 0.9 ;
- export Share V3 borné ;
- résumé Markdown ;
- non-régression Semantics V6 / Resilience V4.

## Politique de livraison

0.9 inaugure un modèle de **milestones** : plusieurs améliorations cohérentes sont regroupées dans une même version visible plutôt que de multiplier les micro-releases.
