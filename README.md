# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est une App Home Assistant de diagnostic **locale, explicative et en lecture seule**. Elle inspecte l'état de l'installation et les YAML autorisés, corrèle les symptômes, comprend les dépendances entre automatisations et transforme le résultat en plan d'action priorisé.

## Milestone 0.9 — du diagnostic technique au triage client

La 0.9 ne se contente plus d'empiler des alertes. Elle répond d'abord à cinq questions simples :

1. **Quel est l'état global de mon Home Assistant ?**
2. **Qu'est-ce que je dois corriger en premier ?**
3. **Quel problème a le plus d'impact réel ?**
4. **À quel point HA Doctor est-il sûr de son propre diagnostic ?**
5. **Qu'est-ce qui a réellement changé depuis les scans précédents ?**

Le moteur technique 0.8 reste présent en dessous : Entity Flow, Controller Semantics, lineage, blast radius, temporalité, résilience et Score V5 Preview. La 0.9 ajoute une couche produit qui rend ces informations directement exploitables.

### Doctor View V1

`doctor_view` produit un verdict court et déterministe :

- score technique V4 inchangé ;
- preview V5 séparé ;
- projection après les premières corrections ;
- prochaine meilleure action ;
- nombre d'actions à corriger, investiguer, revoir ou optimiser ;
- confiance du diagnostic ;
- résumé des changements depuis l'historique.

Aucun score historique n'est réécrit par cette couche.

### Triage Board V1

Chaque élément du plan reçoit une vue client commune :

- `lane` : `fix_now`, `investigate`, `review`, `optimize` ou `watch` ;
- `risk_score` de 0 à 100 ;
- niveau de confiance A/B/C/D ;
- type de traitement ;
- effort estimé ;
- blast radius ;
- gain de score estimé lorsqu'un scénario Score V5 existe.

Le tri est calculé localement à partir du rapport déjà produit. Il ne lance aucune nouvelle requête Home Assistant.

### Diagnostic Trust V1

HA Doctor expose maintenant la confiance qu'il accorde à **son propre scan**. Elle tient notamment compte de :

- quality gates ;
- cohérence interne ;
- résolution des flux ;
- erreurs de lineage ;
- cibles dynamiques non résolues ;
- garanties de confidentialité et de lecture seule.

Une installation peut donc avoir un bon score tout en ayant un scan incomplet, et cette différence reste visible.

### Report Self-Check V1

Avant présentation, HA Doctor contrôle son propre rapport :

- identité version/schéma ;
- bornes des scores ;
- compteurs de sévérité ;
- unicité des findings et actions ;
- cohérence du plan d'action ;
- cohérence contrôleurs/paires ;
- cohérence de la résilience ;
- métriques de flux et temporalité ;
- invariants de confidentialité ;
- sérialisation JSON et taille du rapport.

L'auto-contrôle est lui-même exposé dans le rapport et via `/api/self-check`.

## Intelligence technique conservée

### Entity Flow V3.1

Le graphe distingue :

- `triggers_on` — entités qui déclenchent une automatisation ;
- `controls` — entités réellement commandées ;
- `calls` — scripts, scènes ou automatisations invoqués ;
- `reads` — entités consultées ;
- cibles dynamiques résolues et leur confiance.

HA Doctor n'exécute pas les templates Jinja. La résolution reste statique et prudente.

### Controller Semantics V6

Le moteur sait notamment reconnaître :

- conditions d'état mutuellement exclusives ;
- ensembles de modes littéraux exclusifs ;
- commandes déterministes identiques ;
- réconciliations au démarrage ;
- handoffs par helper ;
- interlocks correctifs ;
- interlocks médiés par une troisième automatisation.

Une paire n'est déclassée que lorsqu'une preuve statique suffisante existe.

### Resilience V4

La résilience distingue désormais :

- contrôle physique ;
- contrôle de helper ;
- usage observationnel ;
- dépendance externe ;
- dépendance de configuration locale.

Les triggers `numeric_state` fail-closed et les branches explicites de repli peuvent être reconnus. Une simple lecture destinée à une notification ne gonfle plus artificiellement le risque physique.

### Entity Lineage + Registry Blast Radius

HA Doctor peut suivre une source vers des entités dérivées puis vers les automatisations utilisatrices. Une panne d'intégration peut donc être reliée à son impact réel même lorsque l'automatisation lit un capteur template intermédiaire.

### Temporal V3.1

L'historique local distingue :

- nouveau ;
- persistant ;
- récurrent ;
- réellement résolu ;
- toujours détecté mais déclassé.

Les rescans rapprochés ne suffisent pas à transformer artificiellement un diagnostic en problème persistant.

## Exports 0.9

### Rapport support V3

`/api/download-share` produit `ha-doctor-support.json` :

- cible ~28 Ko ;
- plafond dur 32 Ko ;
- toutes les identités d'actions et de findings sont conservées ;
- le graphe complet, les états bruts, le YAML brut et les secrets sont exclus ;
- Doctor View et Self-Check sont inclus.

### Résumé lisible

`/api/download-support-summary` produit `ha-doctor-summary.md`, un document court avec verdict, score, prochaines actions, évolution et auto-contrôle.

## API locale principale

- `/api/status`
- `/api/version`
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
- `/api/doctor-view`
- `/api/self-check`
- `/api/share-report`
- `/api/diagnostic?id=DX-...`
- `/api/download-share`
- `/api/download-support-summary`
- `/api/download-anonymized`
- `/health`

## Confidentialité et sécurité

HA Doctor n'effectue que des lectures.

- `/ha_config` est monté en lecture seule ;
- `secrets.yaml` n'est pas lu ;
- `.storage` n'est pas parcouru directement ;
- les registres passent par l'API WebSocket Home Assistant ;
- bases de données, clés privées, certificats et sauvegardes binaires sont exclus ;
- les valeurs brutes des états ne sont pas persistées ;
- le token Supervisor n'est pas enregistré ;
- le YAML reparsé et le texte brut des templates ne sont pas persistés dans l'historique ;
- aucune correction, suppression, désactivation ou redémarrage n'est exécuté automatiquement ;
- aucun service d'IA externe n'est utilisé pour le diagnostic.

## Installation

Dans Home Assistant :

1. **Paramètres → Apps → App Store**.
2. **⋮ → Dépôts**.
3. Ajouter `https://github.com/loic38960/ha-doctor`.
4. Rechercher les mises à jour.
5. Installer ou mettre à jour **HA Doctor**.
6. Démarrer l'App et ouvrir l'interface Web.

## Validation et packaging

La CI exécute à chaque push :

- tous les tests unitaires historiques et 0.9 ;
- compilation de tous les modules Python ;
- validation JavaScript de l'empilement UI ;
- cohérence de version ;
- construction réelle de l'image Home Assistant App ;
- vérification des modules packagés ;
- smoke tests du runtime HTTP ;
- tests des exports JSON/Markdown ;
- tests de non-régression Controller Semantics V6 et Resilience V4.

Le Dockerfile conserve `COPY *.py ./`, afin qu'un nouveau moteur Python ne soit pas oublié dans l'image.

## Politique de versions

À partir de 0.9, les versions visibles sont traitées comme des **milestones**. Les évolutions internes sont regroupées autant que possible afin d'éviter une succession de micro-versions pour quelques règles isolées.

HA Doctor reste expérimental : son score est un indicateur de diagnostic et de maintenance, pas une certification de sécurité ou de conformité.
