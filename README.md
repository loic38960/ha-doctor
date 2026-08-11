# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est une App Home Assistant de diagnostic **locale, explicative et strictement en lecture seule**. Elle analyse l'installation, les registres accessibles par l'API et les YAML autorisés, puis transforme les symptômes en causes racines, risques, décisions et playbooks manuels.

## HA Doctor 0.14 — Consolidated Decision Engine

0.14 consolide plusieurs générations du moteur en un pipeline public unique :

1. **une acquisition Home Assistant** avec un snapshot d'états éphémère ;
2. analyses statiques YAML / automatisations / registres ;
3. Entity Flow, lineage, blast radius et résilience ;
4. **Condition Semantics V9** ;
5. **Temporal V5 publication-aware** ;
6. **Decision Engine V2** ;
7. **Self-Check V6 natif** ;
8. release gate ;
9. publication du score historique uniquement si le rapport est autorisé.

Les wrappers de scanner 0.12 → 0.13 ne sont plus utilisés par le runtime 0.14. Cette consolidation évite de recalculer plusieurs fois les mêmes couches produit et supprime les validations qui maquillaient temporairement un rapport courant en ancienne version.

## Décisions opérationnelles

### Decision Engine V2

Chaque diagnostic du plan conserve son identité et reçoit :

- une pertinence opérationnelle `high`, `medium` ou `low` ;
- un score de priorité d'exécution ;
- une voie opérationnelle ;
- un playbook manuel ;
- des critères de réussite ;
- une indication explicite de préparation à la réparation.

Les voies sont :

- `fix_now` — corrections prioritaires avec preuve forte ;
- `logic_review` — arbitrage ou logique à comprendre avant modification ;
- `restore_if_needed` — dépendance externe qui a un impact réel ;
- `watch` — incident visible mais sans blast radius d'automatisation actuel ;
- `optimize` — simplification ou dette technique non urgente.

Un équipement `unavailable` n'est donc plus automatiquement placé devant un problème de logique simplement parce qu'il possède beaucoup d'entités.

### Playbooks V2

HA Doctor **n'applique jamais** le playbook. Il décrit :

- ce qu'il faut vérifier ;
- l'ordre recommandé ;
- le niveau de prudence ;
- ce qui constitue une correction réussie ;
- le principe de rollback.

Aucun auto-fix, suppression, désactivation, redémarrage ou écriture Home Assistant n'est effectué.

## Controller Semantics V9

Le moteur conserve les preuves précédentes :

- états mutuellement exclusifs ;
- modes exclusifs ;
- handoffs par helpers ;
- branches déterministes ;
- interlocks correctifs ;
- interlocks médiés ;
- garde-fous obligatoires littéraux.

V9 ajoute une analyse **branche + trigger + fenêtre numérique**.

Pour chaque chemin qui commande un actionneur, HA Doctor rattache les contraintes `numeric_state` littérales du trigger et de la branche réellement capables d'atteindre cette commande.

Deux commandes opposées peuvent alors être :

- **résolues** si tous leurs chemins sont numériquement disjoints ;
- **maintenues à revoir** si une fenêtre commune existe.

Une fenêtre commune est une preuve de **conflit de politique statique possible**, pas une affirmation que les deux automatisations s'exécutent simultanément. Les templates Jinja ne sont jamais exécutés pour inventer cette preuve.

## Temporal V5 — publication-aware

Le contrat historique reste `published_primary_score_v1`, mais 0.14 ajoute une règle indispensable :

> un score n'est fiable pour le scan suivant que si `publication_complete == true`.

Un rapport bloqué par Self-Check peut être conservé comme candidat de diagnostic, mais :

- il ne reçoit pas de score canonique publié ;
- il ne devient jamais la baseline du scan suivant ;
- il ne peut pas créer un faux `score stable` ;
- la raison de son exclusion reste visible.

La politique publique est `publication_complete_required_v1`.

## Self-Check V6 natif

0.14 abandonne le mécanisme qui transformait temporairement le rapport courant en ancienne version pour rejouer des checks hérités.

Self-Check V6 valide directement :

- version et schémas publics ;
- action plan et identités ;
- Decision Engine et playbooks ;
- voies opérationnelles ;
- preuve des contrôleurs ;
- source de vérité Sécurité / Maintenance ;
- Temporal V5 ;
- garanties de snapshot unique ;
- confidentialité et lecture seule ;
- Flow / consistency ;
- absence de marqueurs publics périmés ;
- **le vrai Share Report V8 généré**.

Une erreur de Self-Check bloque la publication du rapport comme référence historique.

## Entity Attention V3

Les compteurs bruts restent visibles, mais ne déterminent jamais seuls la priorité.

HA Doctor distingue notamment :

- entités indisponibles ;
- états `unknown` stateful ;
- états stateless ignorables ;
- incidents Registry regroupés ;
- blast radius vers les automatisations ;
- dépendances externes réellement critiques ;
- incidents externes sans impact d'automatisation.

Ces derniers restent visibles dans la voie `watch` au lieu d'encombrer les actions principales.

## Résilience

La résilience reste role-aware et Exposure First :

- contrôle physique ;
- contrôle helper ;
- usage observationnel ;
- dépendance externe ;
- dépendance de configuration.

Un contrôle physique réellement non protégé passe devant une dépendance très critique qui possède déjà un fallback faible.

## Share Report V8

`/api/download-share` génère `ha-doctor-support.json`.

Objectifs :

- cible **26 Ko** ;
- plafond dur **30 Ko** ;
- toutes les identités de findings et d'actions conservées ;
- décisions et voies opérationnelles conservées ;
- playbooks principaux compactés ;
- preuve de policy overlap conservée ;
- trace Résilience conservée ;
- vérité temporelle publication-aware conservée ;
- aucun état brut ;
- aucun YAML brut ;
- aucune valeur de secret ;
- aucun graphe de dépendances complet.

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
- `/api/decision-engine`
- `/api/repair-playbooks`
- `/api/operational-decisions`
- `/api/publication-truth`
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
- bases de données, clés privées, certificats et sauvegardes binaires sont exclus ;
- les états bruts ne sont pas persistés ;
- le token Supervisor n'est pas enregistré ;
- le YAML reparsé et les templates bruts ne sont pas persistés dans l'historique ;
- aucune correction automatique n'est effectuée ;
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

La CI exécute notamment :

- l'ensemble des tests unitaires historiques et courants ;
- compilation de toutes les sources Python ;
- validation JavaScript de l'UI ;
- contrôle des contrats 0.14 ;
- contrôle que le scanner 0.14 ne chaîne pas les scanners 0.12/0.13 ;
- contrôle que Self-Check V6 ne rejoue pas les anciens Self-Checks par réécriture du rapport ;
- construction réelle de l'image Home Assistant App ;
- tests V9 policy overlap ;
- tests des voies opérationnelles ;
- tests de l'historique publication-aware ;
- démarrage réel de l'API HTTP dans l'image construite.

## Politique de versions

Les versions publiques sont traitées comme des **milestones**. Les évolutions sont regroupées en lots importants ; les micro-versions sont réservées aux régressions critiques qui nécessitent un hotfix.

HA Doctor reste expérimental : son score est un indicateur de diagnostic et de maintenance, pas une certification de sécurité ou de conformité.
