# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est une App Home Assistant de diagnostic **locale, explicative et strictement en lecture seule**. Elle analyse les états, registres et YAML autorisés, corrèle les symptômes, identifie les causes racines et transforme le résultat en décisions et playbooks manuels.

## HA Doctor 0.16 — Evidence Precision Engine

0.16 part du principe qu'un diagnostic large n'est pas forcément une action large. Le moteur conserve le contexte architectural, mais la priorité client repose maintenant sur **ce qui reste réellement non résolu**.

Pipeline :

1. une acquisition Home Assistant, snapshot éphémère unique ;
2. Flow, lineage, Registry, architecture et analyse statique ;
3. **Condition Semantics V11** ;
4. **Controller Impact V2** ;
5. **Resilience Precision V5** ;
6. classification feedback / actions dupliquées ;
7. **Temporal V7** ;
8. **Decision Engine V4** et ordre canonique ;
9. staging de publication ;
10. **Self-Check V8** ;
11. release gate ;
12. commit/abort puis validation post-commit.

Aucune couche 0.16 ne provoque de seconde lecture des états Home Assistant.

## Controller Impact V2 — unresolved scope

Les versions précédentes pouvaient conserver le blast radius du finding global `HD-AUTO-003` alors que l'analyse sémantique avait déjà résolu la majorité des paires.

0.16 sépare désormais :

- **contexte historique large** : utile pour comprendre l'architecture ;
- **scope physique encore ouvert** : seul scope utilisé pour la priorité opérationnelle.

Le moteur calcule :

- nombre exact de paires physiques non résolues ;
- actionneurs physiques concernés ;
- automatisations réellement présentes dans ces paires ;
- impact pondéré de ce scope précis ;
- paires de helpers conservées séparément.

Un ancien blast radius de 18 automatisations ne peut donc plus être présenté comme l'impact courant si une seule paire physique à deux automatisations reste ouverte.

## Resilience Precision V5 — phase-aware

Une dépendance capteur n'a pas le même risque selon le moment où elle est utilisée.

0.16 distingue statiquement :

- `pre_control_trigger` ;
- `pre_control_decision` ;
- `post_action_confirmation` ;
- `trigger_plus_post_confirmation` ;
- `mixed_feedback_control` ;
- `unresolved_reference_phase`.

Une donnée uniquement utilisée après une commande physique pour confirmer le résultat n'est plus automatiquement assimilée à une dépendance décisionnelle avant action.

Un risque `must_fix` n'est déclassé que si aucune dépendance pré-contrôle non protégée n'est prouvée et qu'une phase plus faible est statiquement identifiable. Le score V4 historique n'est pas recalculé rétroactivement par cette couche.

## Automation Precision V1

### Feedback automation

`HD-AUTO-008` est maintenant qualifié :

- `state_reassertion_feedback` ;
- `state_transition_feedback` ;
- `controlled_entity_feedback` ;
- `feedback_loop_review`.

HA Doctor **ne prétend jamais avoir prouvé une boucle runtime** à partir de cette analyse statique.

### Actions consécutives identiques

Les doublons exacts sont classés comme :

- `side_effect_duplicate` — par exemple deux notifications identiques ;
- `idempotent_control_candidate` ;
- `repeated_script_call` ;
- `service_side_effect_unknown`.

Même lorsqu'un doublon paraît évident, HA Doctor ne le supprime jamais automatiquement.

## Decision Engine V4 — Canonical Decision Order

Une seule politique d'ordre est utilisée dans :

- Action Plan ;
- Decision Engine ;
- Doctor View ;
- `diagnostic_summary.top_actions` ;
- Share Report.

Ordre :

1. voie opérationnelle ;
2. pertinence ;
3. score de priorité de précision ;
4. sévérité ;
5. confiance ;
6. identifiant stable.

Les incidents externes sans blast radius restent dans `watch` et ne remontent pas devant une correction locale prouvée.

## Temporal V7 — baseline publiée visible

La transaction de publication `published_primary_score_v1` reste inchangée.

0.16 rend toutefois la dernière baseline réellement publiée visible même si elle est trop récente pour être utilisée dans un delta à cause de la protection anti-rescan.

Le rapport expose notamment :

- dernière baseline publiée ;
- âge de cette baseline ;
- éligibilité au delta ;
- scan courant devenu ou non baseline canonique ;
- nombre de snapshots publiés incluant le scan courant ;
- score candidat pour le prochain scan.

Un rapport bloqué ne peut toujours jamais devenir une baseline.

## Self-Check V8

Le Self-Check vérifie désormais en plus :

- scope contrôleur exact = paires physiques restantes ;
- liste exacte des automatisations de ce scope ;
- absence d'utilisation du blast radius historique pour la priorité ;
- Resilience phase-aware ;
- classifications de feedback sans faux claim runtime ;
- doublons exacts sans auto-cleanup ;
- **ordre strictement identique** entre Action Plan, Decision Engine et résumé public ;
- Share V10 réel ;
- transaction historique 0.16 estampillée avec les contrats 0.16.

Une incohérence bloque la publication canonique.

## Share Report V10

`/api/download-share` génère `ha-doctor-support.json`.

- cible : **20 Ko** ;
- plafond dur : **24 Ko** ;
- toutes les identités findings/actions conservées ;
- ordre canonique conservé ;
- impact contrôleur exact conservé ;
- preuve événementielle conservée ;
- trace résilience phase-aware conservée ;
- feedback/doublons compactés ;
- visibilité de baseline publiée conservée ;
- aucun état brut ;
- aucun YAML brut ;
- aucune valeur de secret ;
- aucun graphe complet.

## API locale principale

- `/api/status`
- `/api/version`
- `/api/report`
- `/api/summary`
- `/api/doctor-view`
- `/api/self-check`
- `/api/operational-decisions`
- `/api/evidence-precision`
- `/api/decision-order`
- `/api/published-baseline`
- `/api/share-report`
- `/api/download-share`
- `/api/download-support-summary`
- `/health`

## Confidentialité et sécurité

**HA Doctor n'effectue que des lectures.**

- `/ha_config` est monté en lecture seule ;
- `secrets.yaml` n'est pas lu ;
- `.storage` n'est pas parcouru directement ;
- les registres passent par l'API Home Assistant ;
- les états bruts ne sont pas persistés ;
- le token Supervisor n'est pas enregistré ;
- les templates Jinja ne sont pas exécutés pour inventer des preuves ;
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

## Validation CI

La CI valide :

- toute la suite unitaire historique + 0.16 ;
- compilation de tous les modules Python ;
- JavaScript UI ;
- architecture snapshot unique ;
- scope contrôleur exact ;
- phase-aware resilience ;
- feedback et doublons ;
- ordre canonique ;
- contrat de publication 0.16 ;
- Share V10 ;
- build réel de l'image Home Assistant App ;
- imports packagés ;
- démarrage réel de l'API HTTP.

## Politique de versions

Les versions publiques sont des **milestones**. Les micro-versions sont réservées aux régressions critiques nécessitant un hotfix immédiat.

HA Doctor reste expérimental : son score est un indicateur de diagnostic et de maintenance, pas une certification de sécurité ou de conformité.
