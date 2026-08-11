# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est une App Home Assistant de diagnostic **locale, explicative et strictement en lecture seule**. Elle analyse les états, registres et YAML autorisés, corrèle les symptômes, identifie les causes racines et transforme le résultat en décisions et playbooks manuels.

## HA Doctor 0.17 — Resolution & Attribution Engine

0.17 part d'un principe simple : **une revue manuelle ne doit rester dans le rapport que si HA Doctor n'a pas assez de preuve pour la résoudre lui-même**.

Pipeline :

1. une acquisition Home Assistant, snapshot éphémère unique ;
2. Flow, lineage, Registry, architecture et analyse statique ;
3. Condition Semantics V11 et Controller Impact V2 ;
4. Resilience V6 Guard Actionable ;
5. Automation Feedback V2 + Duplicate Semantics V2 ;
6. Missing Reference Intelligence V1 ;
7. Temporal V8 + Score Attribution V1 ;
8. Decision Engine V5 ;
9. staging de publication ;
10. Self-Check V9 sur le rapport et le vrai Share V11 ;
11. release gate ;
12. commit/abort puis validation post-commit.

Aucune couche 0.17 ne provoque de seconde lecture des états Home Assistant.

## Résolution avant revue

Chaque décision reçoit maintenant un état :

- `manual_fix_ready` — preuve suffisante pour proposer une correction manuelle précise ;
- `logic_review_required` — l'intention humaine reste nécessaire ;
- `statically_resolved` — la relation a été expliquée statiquement ;
- `watch_only` — visible mais sans priorité opérationnelle actuelle ;
- `optimization` ;
- `external_restore_if_needed`.

Le score technique historique n'est pas artificiellement augmenté par cette couche.

## Automation Feedback V2

Une automation qui déclenche sur une entité qu'elle commande n'est pas automatiquement une boucle.

HA Doctor distingue notamment :

- une transition terminale : trigger `to: on`, puis commande `off` ; une future réentrée vers `on` est nécessaire pour redéclencher ;
- une réaffirmation du même état ;
- un trigger state large susceptible d'observer sa propre transition ;
- une action pouvant restaurer l'état cible du trigger ;
- les cas encore insuffisamment prouvés.

**Aucune boucle runtime n'est déclarée comme prouvée à partir du YAML seul.**

## Duplicate Semantics V2

Un doublon consécutif exact à effet de bord, par exemple deux notifications identiques, peut devenir une correction `fix_now` avec haute confiance.

La suppression reste toujours manuelle : HA Doctor demande de confirmer que la répétition n'est pas volontaire et conserve `automatic_removal_safe=false`.

## Missing Reference Intelligence V1

Les références absentes sont classées selon leur contexte et leur impact opérationnel.

HA Doctor peut distinguer une référence d'archive d'une référence runtime, mais **n'invente jamais un entity_id de remplacement**.

`replacement_inference_enabled=false` est un invariant contrôlé par le Self-Check.

## Resilience V6 — Guard Actionable

Les dépendances externes sont séparées en :

- pré-contrôle non protégé → `must_fix` ;
- fallback faible → `hardening`.

Pour chaque cas, HA Doctor produit une stratégie manuelle : garde `unavailable/unknown` avant commande physique ou durcissement du fallback pour distinguer une mesure absente d'un zéro numérique.

## Controller Impact V2

La priorité ne repose plus sur le blast radius historique global de `HD-AUTO-003` mais sur les **paires physiques réellement encore ouvertes**.

Le contexte architectural large reste disponible, mais il ne peut plus faire croire qu'un conflit courant concerne 18 automatisations si la dernière paire réelle n'en concerne que deux.

## Temporal V8 — Score Attribution

Le score canonique reste `published_primary_score_v1`.

À partir des snapshots 0.17 publiés, HA Doctor stocke également :

- les scores finaux par domaine ;
- unavailable / unknown ;
- le nombre d'états.

Si la baseline précédente est 0.16.1 et ne contient pas ces détails, le premier rapport 0.17 indique honnêtement :

`baseline_domain_detail_unavailable`

Il ne devine pas la cause d'un ancien delta. Une fois une baseline 0.17 publiée, les scans suivants peuvent expliquer les variations par domaine.

## Decision Engine V5

L'ordre canonique est partagé par :

- Action Plan ;
- Decision Engine ;
- Doctor View ;
- top actions ;
- rapport support.

Le moteur privilégie les corrections prouvées, puis les revues à impact réel, et laisse les incidents externes sans blast radius en surveillance.

## Self-Check V9

Une incohérence bloque la publication canonique. Sont notamment contrôlés :

- identité de tous les contrats 0.17 ;
- snapshot unique et zéro lecture HA supplémentaire ;
- aucune écriture / aucun auto-fix ;
- domaine présent pour chaque décision ;
- playbooks V5 ;
- résolution correcte des doublons et feedbacks ;
- aucune invention de référence ;
- must-fix vs hardening Résilience ;
- honnêteté de l'attribution du score ;
- ordre Action Plan / Decision Engine ;
- vrai fichier support final ;
- transaction d'historique canonique.

## Share Report V11

`/api/download-share` génère `ha-doctor-support.json`.

- cible : **18 Ko** ;
- plafond dur : **22 Ko** ;
- toutes les identités findings/actions conservées ;
- résolution et attribution conservées ;
- scope contrôleur exact conservé ;
- stratégies Résilience conservées ;
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
- `/api/resolution`
- `/api/score-attribution`
- `/api/resilience-guards`
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

La CI valide notamment :

- toute la suite unitaire historique + 0.17 ;
- compilation de toutes les sources Python ;
- JavaScript UI ;
- snapshot HA unique ;
- résolution de transition state ;
- doublon exact manuel uniquement ;
- références absentes sans remplacement inventé ;
- Résilience weak vs unprotected ;
- attribution honnête avec baseline 0.16 ;
- attribution détaillée après baseline 0.17 ;
- stockage canonique des scores par domaine ;
- Share V11 ;
- build réel de l'image Home Assistant App ;
- imports packagés ;
- démarrage réel de l'API HTTP.

Voir aussi [`RELEASE_0.17.0.md`](RELEASE_0.17.0.md).
