# HA Doctor 0.7.0 Alpha

## Objectif

HA Doctor effectue un diagnostic local et en lecture seule d'une installation Home Assistant. Il ne corrige, ne supprime, ne redémarre et ne modifie rien automatiquement.

La 0.7 transforme le scanner en moteur de diagnostic corrélé : les règles statiques, les registres, le graphe d'automatisations et l'historique local sont combinés pour produire des causes racines, un blast radius et un plan d'action final cohérent.

## Chaîne d'analyse

La chaîne actuelle est organisée ainsi :

1. collecte Home Assistant / Supervisor ;
2. analyse YAML, packages et blueprints ;
3. règles statiques sur configuration et automatisations ;
4. triage `unavailable` / `unknown` ;
5. Entity Registry / Device Registry via WebSocket ;
6. corrélation intégration / appareil / cluster ;
7. moteur explicatif local ;
8. nettoyage du graphe de dépendances ;
9. blast radius pondéré ;
10. contexte temporel et régressions ;
11. score V4 ;
12. analyse d'architecture et dette de maintenance ;
13. synchronisation du plan, du résumé et des quality gates ;
14. export et interface.

## Données lues

- API Home Assistant : configuration générale, états courants et services/actions disponibles.
- API Supervisor : informations accessibles au rôle configuré.
- WebSocket Home Assistant via le proxy Supervisor : Entity Registry et Device Registry.
- `/ha_config` : YAML autorisés, montés en lecture seule.

Les états courants sont nécessaires au calcul mais ne sont pas persistés comme historique brut.

## Données explicitement exclues

- `secrets.yaml` / `secrets.yml` ;
- `.storage` en accès fichier direct ;
- bases SQLite ;
- certificats et clés ;
- sauvegardes binaires ;
- token Supervisor ;
- payload brut des registres dans le rapport ;
- valeurs de secrets détectés.

## Graphe de dépendances V2

Le graphe `entity_graph_v2` distingue quatre relations :

- `triggers_on` : entités qui déclenchent une automatisation ;
- `controls` : entités commandées par l'automatisation ;
- `reads` : entités lues sans être trigger ni cible de commande ;
- `entities` : union des entités réelles du nœud.

Les appels de service tels que `switch.turn_on`, `input_number.set_value`, `climate.set_temperature` et `todo.get_items` sont retirés des références d'entités.

Le bloc `dependency_graph_meta` expose le nombre de références avant nettoyage, services filtrés, arêtes d'entités, triggers et contrôles.

## Classification des dépendances

Les entités sont classées afin de calibrer leur impact :

- `actuator` : actionneur physique ou logique pilotable ;
- `sensor` : information utilisée par la logique ;
- `helper` : état de coordination Home Assistant ;
- `optional` : contrôle ou paramètre secondaire ;
- `other`.

Un helper partagé ne doit pas peser comme une pompe, un chauffage, une serrure ou une sirène. Le calcul de `dependency_impact` applique donc un poids fortement inférieur aux helpers.

Chaque diagnostic peut recevoir :

- `impacted_automation_count` ;
- `critical_automation_count` ;
- `helper_only_automation_count` ;
- `trigger_dependency_count` ;
- `control_dependency_count` ;
- `weighted_impact_score` ;
- `score_multiplier` ;
- `top_entities`.

## Architecture

Le bloc `architecture_analysis` est informatif et ne constitue pas une pénalité automatique.

Il expose :

- `complexity_score` / `complexity_label` ;
- `entity_dependency_count` ;
- `entity_edge_count` ;
- `shared_actuator_count` ;
- `helper_hub_count` ;
- `trigger_hub_count` ;
- `closed_loop_count` ;
- `top_hotspots` ;
- `shared_actuators` ;
- `helper_hubs` ;
- `trigger_hubs` ;
- `closed_loops` ;
- `automation_risk_profiles` ;
- `top_sources`.

Le but est d'identifier les zones où une future modification est susceptible d'avoir un effet large.

## Corrélation des causes racines

Le moteur réutilise les incidents déterministes issus des registres :

- intégration hors ligne ;
- intégration partiellement dégradée ;
- appareil isolé hors ligne ;
- cluster d'appareils partageant un motif ;
- observations transitoires.

Les diagnostics génériques `HD-ENT-001` et `HD-ENT-003` peuvent rester dans les findings techniques mais sont retirés du plan d'action si des causes racines expliquent déjà le volume d'entités concerné.

`HD-REG-002` de faible confiance est également supprimé du plan lorsque le registre ne fournit aucune preuve d'orphelin probable.

## Temporalité V2

L'historique local est limité aux 20 derniers scans.

Chaque snapshot conserve uniquement :

- date ;
- score V4 ;
- éventuel score historique V3 ;
- diagnostics actifs ;
- incidents de registre ;
- compteurs de priorité ;
- compteurs `unavailable` / `unknown` ;
- quelques métriques d'architecture ;
- score de dette de maintenance.

Un diagnostic peut être :

- `baseline` ;
- `new` ;
- `persistent` ;
- `recurrent`.

Pour les incidents du registre, un signal ponctuel est moins pénalisé. Sa pondération augmente progressivement s'il persiste sur plusieurs scans.

La migration accepte les anciennes entrées `health_score_v3` afin de ne pas perdre l'historique 0.6.

## Régressions

`regression_analysis` compare le scan courant au précédent et expose :

- variation du score ;
- nouveaux diagnostics ;
- nouvelles priorités immédiates ;
- diagnostics résolus ;
- diagnostics persistants ;
- état `stable`, `improved` ou `degraded` ;
- indicateur `requires_attention`.

Une baisse significative du score ou l'apparition d'un nouveau diagnostic `action_now` peut faire passer le scan en régression.

## Score V4

Modèle : `root_cause_temporal_v4`.

Le score est calculé sur le plan corrélé final, et non sur les volumes bruts d'états.

La pénalité dépend de :

- priorité ;
- sévérité ;
- confiance ;
- persistance ;
- impact de dépendance.

Des plafonds de pénalité par domaine évitent qu'une seule cause produisant de nombreux symptômes ne soit comptée plusieurs fois.

Le rapport expose le détail dans `score_meta.penalty_breakdown` et `score_meta.domain_penalties`.

Le score reste un indicateur Alpha et non une certification.

## Dette de maintenance

`maintenance_debt` est volontairement séparé de `scores`.

Il agrège notamment :

- références absentes ;
- orphelins probables ;
- candidats locaux à revoir ;
- traces de secrets dans archives ;
- couverture partielle des automatisations YAML.

Le but est de montrer qu'une installation peut fonctionner correctement tout en accumulant une dette de configuration.

## Quality gates

Avant présentation du rapport, HA Doctor produit des contrôles sur ses propres entrées :

- API ;
- parsing YAML ;
- résolution des blueprints ;
- disponibilité des registres ;
- confidentialité ;
- nettoyage du graphe ;
- cohérence des compteurs plan/résumé.

Un échec de quality gate doit être visible afin d'éviter de donner une confiance excessive à un rapport incomplet.

## Plan d'action V2

`action_plan` est construit après :

1. tri par priorité / sévérité / confiance ;
2. déduplication ;
3. suppression du bruit expliqué par des causes racines ;
4. contexte temporel ;
5. blast radius.

Chaque action expose un champ `why_now` expliquant pourquoi elle se trouve à cette position.

Le bloc `diagnostic_summary` est ensuite reconstruit à partir de ce plan final afin d'empêcher une divergence entre les compteurs affichés et les actions réellement proposées.

## API 0.7

- `/api/status` : état du scanner ;
- `/api/version` : version et schéma ;
- `/api/report` : rapport complet ;
- `/api/summary` : rapport compact non anonymisé ;
- `/api/insights` : synthèse produit ;
- `/api/actions` : plan d'action ;
- `/api/architecture` : architecture et métadonnées du graphe ;
- `/api/quality` : quality gates, maintenance et privacy ;
- `/api/history` : historique agrégé ;
- `/api/diagnostic?id=...` : détail d'un diagnostic ;
- `/api/download*` : exports ;
- `/health` : healthcheck HTTP.

## Schéma du rapport

Version : `ha-doctor-report/0.7`.

Nouveaux blocs importants :

- `dependency_graph_meta`
- `architecture_analysis`
- `regression_analysis`
- `maintenance_debt`
- `quality_gates`
- `recommendation_queue`
- `report_schema`

Les blocs 0.5/0.6 restent conservés autant que possible pour faciliter la compatibilité.

## Robustesse de l'App

Le Dockerfile 0.7 utilise `COPY *.py ./` afin qu'un nouveau module Python ne soit plus oublié dans l'image Home Assistant.

La CI réalise une construction réelle de l'image puis vérifie :

- présence des modules 0.7 ;
- imports de l'application dans le conteneur ;
- cohérence de version ;
- présence des assets Web ;
- tests unitaires ;
- compilation Python.

Cette vérification cible explicitement les régressions de packaging et de démarrage.

## Interface

Six vues principales :

1. Vue d'ensemble ;
2. Plan d'action ;
3. Architecture ;
4. Intégrations & appareils ;
5. Historique ;
6. Qualité & confidentialité.

Le plan d'action peut être filtré par texte, priorité, domaine et confiance.

## Limites Alpha 0.7

- Jinja totalement dynamique reste difficile à analyser statiquement ;
- le graphe représente la configuration connue, pas toutes les branches d'exécution possibles ;
- l'exclusivité entre automatisations dépendant de templates complexes peut nécessiter une lecture humaine ;
- les logs Home Assistant ne sont pas encore corrélés automatiquement à chaque diagnostic ;
- le maillage Zigbee/MQTT n'est pas encore diagnostiqué en profondeur ;
- les causes racines restent probabilistes ;
- aucune réparation automatique n'est exécutée.
