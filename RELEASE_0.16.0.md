# HA Doctor 0.16.0 — Evidence Precision Engine

## Objectif

0.16 réduit l'écart entre un diagnostic architectural large et le problème réellement encore ouvert.

Le scan réel 0.15 a validé le pipeline de confiance (135/135, publication commitée, Share sous cible), mais a montré qu'un finding global pouvait encore conserver un blast radius trop large alors que la sémantique avait déjà résolu presque tous les contrôleurs.

## Lot livré

### Controller Impact V2

- scope `unresolved_physical_pairs_only` ;
- compte exact des automatisations réellement concernées ;
- cibles physiques exactes ;
- paires helpers séparées ;
- blast radius historique conservé comme contexte mais exclu de la priorité opérationnelle.

### Resilience Precision V5

- `pre_control_trigger` ;
- `pre_control_decision` ;
- `post_action_confirmation` ;
- `trigger_plus_post_confirmation` ;
- `mixed_feedback_control` ;
- phase non résolue explicitement conservée ;
- downgrade uniquement avec preuve statique ;
- aucune exécution de template.

### Automation Precision V1

- feedback sur entité déclenchée + commandée ;
- distinction réaffirmation / transition / review ;
- aucune boucle runtime déclarée comme prouvée ;
- détection indépendante des actions consécutives identiques ;
- classification des doublons à effets de bord ;
- aucun auto-cleanup.

### Decision Engine V4

- impact contrôleur exact injecté dans le diagnostic `HD-AUTO-003` ;
- playbooks enrichis par les preuves de doublon, feedback et résilience ;
- score de priorité recalculé sur l'impact précis ;
- ordre public unique `canonical_decision_order_v1` ;
- Action Plan, Decision Engine, Doctor View et support utilisent le même ordre.

### Temporal V7

- dernière baseline publiée visible indépendamment de son éligibilité au delta ;
- âge et éligibilité exposés ;
- scan courant marqué baseline canonique après commit ;
- snapshot historique 0.16 estampillé avec les contrats 0.16 ;
- rapport bloqué toujours exclu de l'historique canonique.

### Self-Check V8

- identité 0.16 complète ;
- scope exact contrôleur ;
- identité de l'ordre canonique ;
- validation Resilience phase-aware ;
- validation feedback/doublons sans claims dangereux ;
- Share V10 final ;
- validation post-commit de la baseline courante.

### Share V10

- cible 20 Ko ;
- plafond 24 Ko ;
- toutes les identités findings/actions ;
- preuves de précision importantes ;
- aucun état brut, YAML brut, secret ou graphe complet.

## Sécurité

HA Doctor reste strictement en lecture seule.

Aucun auto-fix. Aucun redémarrage. Aucune suppression. Aucune écriture de configuration Home Assistant. Aucune lecture d'état supplémentaire introduite par le moteur de précision.
