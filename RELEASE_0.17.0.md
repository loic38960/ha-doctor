# HA Doctor 0.17.0 — Resolution & Attribution Engine

0.17 réduit encore la quantité de diagnostics laissés à l'utilisateur quand une preuve statique suffisante existe, sans augmenter artificiellement le score technique et sans écrire dans Home Assistant.

## Objectifs

- résoudre statiquement les feedbacks d'automatisation dont la transition est déterministe ;
- promouvoir un doublon exact à effet de bord vers une correction manuelle prête ;
- classer les références absentes sans inventer d'entity_id de remplacement ;
- transformer les alertes de résilience en stratégies de garde explicites ;
- conserver un ordre unique entre rapport, UI et export support ;
- enregistrer les scores publiés par domaine pour expliquer les futurs mouvements de score ;
- réduire le Share Report sous 18 Ko tout en conservant toutes les identités finding/action.

## Automation Feedback V2

Une automation déclenchée sur une entité qu'elle pilote n'est plus automatiquement laissée en revue.

Le moteur distingue notamment :

- `terminating_state_transition` : un trigger `to: on` suivi d'une commande `off` s'éloigne de l'arête qui a déclenché l'exécution ; une nouvelle exécution nécessite une future réentrée ;
- `self_retrigger_candidate` : trigger state large susceptible d'observer sa propre transition ;
- `trigger_state_reentry_candidate` : l'action peut rétablir l'état cible du trigger ;
- `state_reassertion_feedback` ;
- `controlled_entity_feedback`.

Aucune boucle runtime n'est déclarée comme prouvée à partir de cette analyse statique.

## Duplicate Semantics V2

Un doublon consécutif exact classé `side_effect_duplicate` devient `manual_fix_ready`.

Il peut donc passer de `logic_review` à `fix_now`, mais :

- la suppression reste manuelle ;
- le playbook demande de confirmer que la répétition n'est pas volontaire ;
- `automatic_removal_safe` reste faux.

## Missing Reference Intelligence V1

`HD-CFG-001` est enrichi avec :

- références d'archive/inactives ;
- références runtime à faible impact ;
- références runtime utilisées par des automatisations.

HA Doctor n'invente jamais de remplacement. `replacement_inference_enabled=false` est un invariant de release.

## Resilience V6 — Guard Actionable

Les dépendances `must_fix` reçoivent une stratégie de garde explicite avant commande physique.
Les dépendances `hardening` avec fallback faible reçoivent une stratégie distincte afin de ne pas confondre mesure manquante et zéro numérique.

La séparation native reste :

- pré-contrôle non protégé → `must_fix` ;
- fallback faible → `hardening`.

## Decision Engine V5

Chaque décision reçoit un `resolution_status` :

- `manual_fix_ready` ;
- `logic_review_required` ;
- `watch_only` ;
- `optimization` ;
- `statically_resolved` ;
- `external_restore_if_needed`.

Le moteur tente donc de résoudre la preuve avant de demander une revue humaine.

## Temporal V8 — Domain Attribution

Le contrat canonique `published_primary_score_v1` reste inchangé.

À partir des snapshots 0.17 publiés, l'historique stocke également :

- score final par domaine ;
- compteurs unavailable/unknown ;
- nombre total d'états.

Le premier scan 0.17 peut honnêtement retourner `baseline_domain_detail_unavailable` si la baseline 0.16.1 ne contient pas ces données. Aucune cause du delta n'est inventée.

À partir de la baseline 0.17 suivante, HA Doctor peut produire des deltas par domaine et des signaux d'inventaire.

## Self-Check V9

Le Self-Check bloque la publication si :

- un playbook n'utilise pas le contrat courant ;
- une décision n'a pas de domaine ;
- un doublon exact prêt à corriger n'est pas classé correctement ;
- un feedback statiquement résolu reste présenté comme conflit manuel ;
- une référence absente contient un remplacement inventé ;
- un risque résilience non protégé est déclassé ;
- l'attribution du score prétend connaître des domaines absents de la baseline ;
- l'ordre Action Plan / Decision Engine diverge ;
- le support export dépasse son plafond dur ;
- les invariants read-only sont violés.

## Share Report V11

- cible : 18 Ko ;
- plafond : 22 Ko ;
- toutes les identités finding/action conservées ;
- preuves de résolution conservées ;
- attribution du score conservée ;
- scope contrôleur exact conservé ;
- stratégies de garde résilience conservées ;
- aucun état brut ;
- aucun YAML brut ;
- aucune valeur de secret.

## Invariants

**HA Doctor n'effectue que des lectures.**

0.17 n'ajoute aucune lecture d'état Home Assistant après le snapshot initial, n'exécute aucun template pour inventer des preuves et ne modifie jamais la configuration.
