# HA Doctor 0.12.0 — Temporal Truth Engine

0.12 corrige une classe de défaut découverte sur un vrai rapport 0.11 : l'historique compact pouvait conserver un score intermédiaire antérieur à la finalisation du rapport. Le rapport visible et le snapshot historique pouvaient donc diverger et produire à tort un message « score stable ».

## Temporal V4 — score publié canonique

- nouveau contrat historique `published_primary_score_v1` ;
- `final_primary_score` devient la source de vérité du snapshot ;
- `health_score_v3` est synchronisé pour compatibilité ;
- le score preview est stocké séparément ;
- aucun état HA brut, YAML brut ou secret n'est ajouté à l'historique.

## Migration sans deviner

Les snapshots antérieurs à 0.12 ne sont pas considérés comme une preuve du score réellement publié. HA Doctor conserve leur ancienne valeur comme `legacy_previous_score_candidate`, mais ne l'utilise jamais pour calculer un delta. Le premier scan 0.12 démarre automatiquement une nouvelle série canonique.

## Public Contract Truth

0.12 synchronise les identités exposées au client :

- action plan : `correlated_action_plan_v4_temporal_truth` ;
- source finale : `final_cross_validated_action_plan_v120` ;
- controller review : `controller_review_summary_v3_evidence` ;
- temporal : `temporal_v4_canonical_published_score`.

Les quality gates ne réutilisent plus de texte de génération obsolète comme « par V6 » : ils décrivent la preuve courante, notamment les overlaps littéraux et les paires physiques restant à revoir.

## Self-Check V4

Le moteur contrôle les invariants 0.10/0.11, le score courant écrit dans le snapshot canonique, l'absence de faux delta sur historique legacy, la fraîcheur des contrats publics et le Share Report V6 réellement généré.

## Share Report V6

Le support export conserve `temporal_truth`, la confiance du score précédent, le contrat historique, les contrats publics, ainsi que les preuves contrôleur et résilience. La cible reste 28 KiB, limite dure 32 KiB.

## Confidentialité

0.12 reste entièrement en lecture seule. Aucun état brut, YAML brut, contenu de `secrets.yaml` ou valeur de secret n'est persisté dans le rapport support ou l'historique temporel.
