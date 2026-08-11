# HA Doctor 0.13.0 — Decision Engine

0.13 est une release produit complète. Elle ne cherche pas à augmenter artificiellement le score : elle transforme le diagnostic corrélé en décisions exploitables, réduit le poids du bruit opérationnel et renforce la preuve sur les derniers conflits de contrôleurs.

## Condition Semantics V8 — Mandatory Guard Matrix

- conserve toute la logique V7 de fenêtres numériques et d'intentions déterministes ;
- ajoute une matrice de garde-fous d'état obligatoires ;
- une paire physique n'est résolue que si les deux automatisations imposent des états littéraux incompatibles sur le même helper/état ;
- aucune exécution de template Jinja ;
- un overlap numérique reste un indice de concurrence, jamais une preuve suffisante pour innocenter une paire ;
- les cas sans preuve restent explicitement en revue.

## Decision Engine V1

Chaque diagnostic du plan final reçoit :

- une pertinence opérationnelle `high / medium / low` ;
- un niveau de préparation : `ready_for_manual_change`, `needs_logic_review`, `external_dependency`, `optimization` ou `observe_only` ;
- un playbook manuel concret ;
- des critères de réussite ;
- un principe de rollback ;
- `automatic_fix=false` et `read_only=true`.

Les playbooks spécialisés couvrent notamment les double writers, secrets actifs, Integral sur source non numérique, actions dupliquées, conflits de contrôleurs, résilience externe, références manquantes et incidents registre.

## Entity Attention V2

Les nombres bruts `unavailable` / `unknown` restent mesurés, mais ne dictent plus la priorité produit. HA Doctor sépare désormais :

- incidents registre avec impact réel sur des automatisations ;
- incidents registre sans impact d'automatisation ;
- diagnostics à fort impact de dépendance ;
- bruit brut restant visible pour maintenance.

## Product Intelligence V5

- action plan : `correlated_action_plan_v5_decision_engine` ;
- source : `final_decision_action_plan_v130` ;
- controller review : `controller_review_summary_v4_guard_matrix` ;
- doctor view : `doctor_view_v5_decision_engine` ;
- qualité : nouveau gate Decision Engine ;
- résumé exécutif enrichi avec les actions prêtes, revues logiques et dépendances externes.

## Historique canonique

Le contrat de score reste `published_primary_score_v1`. 0.13 ajoute un wrapper de métadonnées afin que le snapshot final porte réellement :

- `report_version=0.13.0` ;
- `report_schema=ha-doctor-report/0.13` ;
- le modèle du plan 0.13 ;
- la source finale 0.13 ;
- le Decision Engine ;
- Condition Semantics V8.

Aucune migration par supposition n'est introduite.

## Share Report V7

Le paquet support conserve sous 28/32 KiB autant que possible :

- Temporal Truth ;
- Decision Engine compact ;
- pertinence opérationnelle ;
- premier pas de réparation pour les principales actions ;
- matrice de garde-fous contrôleurs ;
- preuves de résilience ;
- contrats publics.

## API

Nouveaux endpoints :

- `/api/decision-engine`
- `/api/repair-playbooks`

`/api/version` expose également le Decision Model et le Condition Model.

## Confidentialité et sécurité

HA Doctor reste strictement en lecture seule :

- aucun changement de configuration Home Assistant ;
- aucun redémarrage, suppression ou désactivation automatique ;
- aucune valeur de secret dans les playbooks ;
- aucune persistance d'états HA bruts ou de YAML brut ;
- aucun état Home Assistant supplémentaire lu par la couche 0.13.
