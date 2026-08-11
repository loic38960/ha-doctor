# HA Doctor 0.14.0 — Consolidated Decision Engine

0.14 est une release de consolidation majeure construite à partir des défauts révélés par le vrai rapport 0.13.

## Pourquoi cette version existe

Le scan 0.13 a montré trois problèmes structurels :

1. le Self-Check pouvait échouer sur `executive_mentions_v7` alors que le rapport public était déjà en V8 ;
2. un rapport bloqué pouvait malgré tout recevoir le contrat historique canonique et risquer de devenir la baseline du scan suivant ;
3. le Share Report V7 dépassait sa cible souple (environ 30,3 Ko pour une cible de 28 Ko).

Au lieu de corriger ces points avec plusieurs micro-versions, 0.14 remplace les mécanismes responsables.

## Pipeline consolidé

Le runtime 0.14 n'appelle plus les scanners 0.12 ou 0.13.

Pipeline public :

`acquisition unique -> V9 semantics -> Temporal V5 -> Product/Decision V2 -> Self-Check V6 -> Release Gate -> publication historique`

Cela supprime les phases imbriquées et les validations qui transformaient temporairement le rapport courant en ancienne version.

## Condition Semantics V9

V9 conserve V8 et ajoute des profils de chemins liés aux triggers et branches :

- contraintes `numeric_state` littérales du trigger ;
- contraintes numériques de la branche ;
- intent déterministe de la commande ;
- comparaison des chemins opposés.

Deux chemins sont déclarés exclusifs uniquement si leur intersection numérique est impossible.

Si une fenêtre commune reste, le moteur produit un `policy_overlap` statique. Il ne prétend pas que deux automatisations s'exécutent simultanément.

Le cas réel ayant motivé cette couche est générique : une branche peut commander `off` au-dessus d'un seuil alors qu'un autre contrôleur autorise `on` jusqu'à un seuil supérieur. HA Doctor doit exposer cette zone comme politique à arbitrer.

## Decision Engine V2

Les diagnostics sont séparés en cinq voies :

- `fix_now` ;
- `logic_review` ;
- `restore_if_needed` ;
- `watch` ;
- `optimize`.

Les incidents Registry sans impact d'automatisation passent dans `watch` au lieu de monopoliser la file d'investigation.

Les playbooks passent en V2 et peuvent intégrer directement la preuve de policy overlap ou les automatisations risquées de Résilience.

## Temporal V5

Le contrat reste `published_primary_score_v1`, avec une politique publique supplémentaire :

`publication_complete_required_v1`

Un snapshot n'est une référence de score fiable que si :

- il possède le contrat canonique ;
- `publication_complete == true` ;
- son score final est présent.

Un rapport bloqué :

- conserve éventuellement un score candidat ;
- ne possède pas de `score_contract` canonique ;
- ne possède pas de `final_primary_score` canonique ;
- ne peut jamais devenir la baseline du scan suivant.

## Self-Check V6 natif

Self-Check V6 ne réécrit jamais le rapport en 0.11/0.12/0.13.

Il valide directement le contrat 0.14 :

- identités publiques ;
- action plan ;
- Decision Engine ;
- tous les playbooks ;
- policy overlap / exclusions numériques ;
- sécurité et maintenance source-derived ;
- temporal publication-aware ;
- snapshot unique et confidentialité ;
- Flow et consistency ;
- absence de labels publics périmés ;
- Share Report V8 réellement généré.

## Share Report V8

Le rapport support est reconstruit autour des besoins support réels plutôt que par empilement des anciens exports.

Contrat :

- cible 26 Ko ;
- plafond 30 Ko ;
- toutes les identités findings/actions conservées ;
- voies décisionnelles conservées ;
- principaux playbooks conservés ;
- policy overlap conservé ;
- Résilience conservée ;
- Temporal V5 conservé ;
- aucun état brut, YAML brut ou secret.

## CI

La CI 0.14 vérifie notamment :

- tests historiques + nouveaux tests 0.14 ;
- compilation Python ;
- JavaScript UI ;
- absence de `scanner_v120` / `scanner_v130` dans le scanner public 0.14 ;
- absence de réécriture legacy dans Self-Check V6 ;
- build réel de l'App Home Assistant ;
- policy overlap 98–100 et exclusion numérique disjointe ;
- voie `watch` pour les Registry sans blast radius ;
- rejet d'un snapshot bloqué comme baseline ;
- démarrage réel du runtime HTTP 0.14.

## Sécurité

HA Doctor reste strictement en lecture seule. Aucune modification automatique de Home Assistant n'est effectuée.
