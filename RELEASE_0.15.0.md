# HA Doctor 0.15.0 — Trust & Publication Engine

## Pourquoi cette milestone

Le premier rapport réel 0.14 a confirmé les nouvelles voies opérationnelles et l'analyse V9, mais a aussi révélé deux défauts d'ordre :

- `public_contract_truth.share_schema_fresh=false` alors que le Share V8 final était correct ;
- `single_snapshot_evidence=false` alors que le scanner utilisait bien un snapshot unique.

La cause était la même : la vérité publique et la confiance étaient calculées avant que leurs preuves finales soient installées.

0.15 corrige ce problème structurel et ajoute une transaction de publication complète.

## Trust-first pipeline

Ordre 0.15 :

1. acquisition unique ;
2. preuve snapshot installée ;
3. Temporal V6 ;
4. contrat public installé ;
5. Product/Decision ;
6. stage historique non canonique ;
7. Self-Check V7 sur le vrai export final ;
8. release gate ;
9. commit ou abort ;
10. validation post-commit avec révocation possible.

## Publication Transaction V1

Un scan commence comme `publication_candidate` sans `score_contract` ni `final_primary_score`.

Seul un rapport entièrement validé peut être promu en `published_canonical`.

Un échec tardif retire les champs canoniques : un rapport bloqué ne peut donc jamais devenir baseline du scan suivant.

## Condition Semantics V10

V10 ajoute la sémantique des événements `numeric_state` : l'entrée dans une plage est distinguée d'un état continu.

Le moteur qualifie les overlaps en :

- `crossing_event_window` ;
- `event_vs_policy_window` ;
- `state_policy_window`.

Un overlap statique ne devient jamais une affirmation d'exécution simultanée ou de boucle continue.

## Decision Engine V3

- operational summary unique ;
- playbooks événementiels pour les overlaps de contrôleurs ;
- conservation des voies `fix_now`, `logic_review`, `restore_if_needed`, `watch`, `optimize` ;
- les incidents Registry sans blast radius restent en `watch`.

## Self-Check V7

- validation native du contrat courant ;
- contrôle explicite contrat-before-truth ;
- contrôle explicite snapshot-before-trust ;
- validation du Share V9 qui contient le Self-Check final ;
- validation post-commit ;
- possibilité de révoquer une publication incohérente.

## Share V9

- cible 22 Ko ;
- plafond 26 Ko ;
- toutes les identités findings/actions conservées ;
- suppression des listes d'exemples et ventilations de domaines inutiles au support ;
- décision, policy overlap événementiel, résilience, publication et Self-Check conservés.

## Sécurité

Toujours strictement en lecture seule :

- aucun auto-fix ;
- aucune écriture Home Assistant ;
- aucune lecture d'état supplémentaire ;
- aucun état brut, YAML brut ou secret persisté dans les exports.
