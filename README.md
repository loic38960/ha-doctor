# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est une App Home Assistant de diagnostic **locale, explicative et strictement en lecture seule**. Elle analyse les états, registres et YAML autorisés, corrèle les symptômes, identifie les causes racines et transforme le résultat en décisions et playbooks manuels.

## HA Doctor 0.15 — Trust & Publication Engine

0.15 durcit le passage entre **diagnostic interne** et **rapport publiable**.

Pipeline public :

1. une acquisition Home Assistant avec un snapshot éphémère unique ;
2. la preuve de ce snapshot est installée immédiatement dans `scan_performance` ;
3. analyses statiques, Flow, lineage, Registry, résilience ;
4. **Condition Semantics V10** ;
5. **Temporal V6** ;
6. installation du contrat public courant ;
7. **Decision Engine V3** ;
8. staging non canonique dans l'historique ;
9. **Self-Check V7** sur le rapport courant et le vrai Share V9 final ;
10. release gate ;
11. commit ou abort de la transaction de publication ;
12. validation post-commit avec possibilité de révocation.

Aucun scan bloqué ne peut devenir une baseline de score.

## Trust-first ordering

Le rapport 0.14 réel a révélé deux problèmes d'ordre :

- le contrat Share était évalué avant d'être installé, ce qui créait un faux `share_schema_fresh=false` ;
- la preuve de snapshot unique était ajoutée après le calcul de confiance, ce qui produisait `single_snapshot_evidence=false` malgré une acquisition correcte.

0.15 impose maintenant ces invariants :

- contrat courant installé **avant** `public_contract_truth` ;
- preuve d'acquisition installée **avant** Doctor Trust ;
- Self-Check contrôle explicitement les deux ;
- CI vérifie l'ordre du pipeline.

## Publication Transaction V1

L'historique fonctionne désormais comme une transaction en deux phases.

### Stage

Le scan courant est enregistré comme candidat :

- `publication_complete=false` ;
- aucun `score_contract` canonique ;
- aucun `final_primary_score` ;
- rôle `publication_candidate`.

### Commit

Le score n'est promu que si :

- Self-Check V7 ne bloque pas ;
- l'export final est valide ;
- les contrats publics sont cohérents ;
- la preuve de snapshot unique est présente ;
- le release gate autorise la publication.

Le snapshot reçoit alors `published_primary_score_v1` et devient une baseline possible.

### Abort / revoke

Si un contrôle final échoue :

- la transaction est avortée ;
- les champs canoniques sont retirés ;
- le candidat reste visible pour diagnostic ;
- il ne peut jamais servir de référence au scan suivant.

## Condition Semantics V10 — Event Window Policy

V9 savait déjà détecter une fenêtre numérique de politiques opposées. V10 ajoute une distinction essentielle :

**un trigger `numeric_state` est un événement de franchissement, pas un état continuellement exécuté.**

HA Doctor distingue donc :

- `crossing_event_window` — deux commandes opposées liées à des franchissements numériques ;
- `event_vs_policy_window` — un franchissement face à une autre politique ;
- `state_policy_window` — overlap sans preuve de sémantique de franchissement.

Une fenêtre commune reste un point de logique à revoir, mais HA Doctor ne prétend plus qu'elle prouve une exécution simultanée ou une boucle continue.

Pour les conflits événementiels, le playbook demande d'abord de décider si le comportement est un handoff volontaire, une hystérésis implicite ou un véritable conflit d'ownership.

## Decision Engine V3

Les voies restent :

- `fix_now` ;
- `logic_review` ;
- `restore_if_needed` ;
- `watch` ;
- `optimize`.

0.15 ajoute un **Operational Summary** unique utilisé par le rapport, l'UI et l'export support. Le résumé client ne mélange plus les 6 incidents `watch` avec les revues logiques principales.

Les incidents Registry sans blast radius automation restent visibles mais ne passent pas devant un problème de logique ou de sécurité.

## Self-Check V7 — final export truth

Self-Check V7 valide directement le contrat courant, sans maquiller le rapport en ancienne version.

Il contrôle notamment :

- identité version / schémas / modèles ;
- ordre contrat → vérité publique ;
- preuve snapshot unique visible par Doctor Trust ;
- identité Action Plan ↔ Decision Engine ;
- voies opérationnelles ;
- sémantique événementielle V10 ;
- source de vérité Sécurité / Maintenance ;
- Temporal V6 ;
- confidentialité et lecture seule ;
- **le vrai Share V9 qui contient lui-même le Self-Check final**.

Après commit historique, un dernier contrôle vérifie encore :

- transaction réellement commitée ;
- snapshot marqué publié ;
- contrats publics toujours frais ;
- export toujours sous le plafond dur.

Ce contrôle peut révoquer la publication.

## Share Report V9

`/api/download-share` génère `ha-doctor-support.json`.

Nouvelle cible :

- **22 Ko** cible ;
- **26 Ko** plafond dur.

Le rapport support conserve :

- toutes les identités des findings ;
- toutes les identités des actions ;
- voies opérationnelles ;
- top playbooks ;
- preuve de policy overlap événementiel ;
- trace Résilience ;
- transaction de publication ;
- Self-Check compact ;
- vérité des contrats publics.

Il ne recopie plus les listes d'exemples `unavailable/unknown` ni la ventilation complète des domaines, qui apportaient beaucoup de poids sans aider l'analyse support.

Il n'inclut jamais : états bruts, YAML brut, valeur de secret ou graphe complet.

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
- `/api/operational-decisions`
- `/api/event-policy`
- `/api/publication-transaction`
- `/api/share-report`
- `/api/diagnostic?id=DX-...`
- `/api/download-share`
- `/api/download-support-summary`
- `/api/download-anonymized`
- `/health`

## Confidentialité et sécurité

**HA Doctor n'effectue que des lectures.**

- `/ha_config` est monté en lecture seule ;
- `secrets.yaml` n'est pas lu ;
- `.storage` n'est pas parcouru directement ;
- les registres passent par l'API WebSocket Home Assistant ;
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

La CI vérifie notamment :

- tous les tests unitaires historiques et 0.15 ;
- compilation de tous les modules Python ;
- JavaScript UI ;
- ordre trust-first du pipeline ;
- contrat public installé avant son évaluation ;
- sémantique de franchissement `numeric_state` ;
- stage / commit / abort de l'historique ;
- révocation des champs canoniques ;
- construction réelle de l'image Home Assistant App ;
- import des modules packagés ;
- démarrage réel de l'API HTTP.

## Politique de versions

Les versions publiques sont des **milestones**. Les micro-versions sont réservées aux régressions critiques nécessitant un hotfix immédiat.

HA Doctor reste expérimental : son score est un indicateur de diagnostic et de maintenance, pas une certification de sécurité ou de conformité.
