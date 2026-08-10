# HA Doctor 0.10.0 — Engine Candidate

0.10.0 est un lot moteur massif construit sur le pipeline d'acquisition mono-snapshot validé en 0.8.8/0.9.0. Le but n'est pas d'ajouter du bruit mais de rendre chaque diagnostic plus explicable, plus priorisable et plus testable.

## Moteur

- Controller Semantics V7 conserve les conflits non prouvés et ajoute des preuves de chevauchement numérique au lieu de fabriquer un faux PASS.
- Resilience Recommendations V3 corrige la règle de sélection : un contrôle physique réellement non protégé passe avant un fallback seulement faible, même si sa criticité brute est inférieure à 60.
- Les helpers internes restent séparés des SPOF externes.
- Le pipeline garde une seule lecture réseau des états Home Assistant.

## Intelligence produit

- Niveaux de preuve : `confirmed`, `probable`, `hypothesis`.
- Décomposition explicite du risk score.
- Gain Score V5 estimé pour davantage de diagnostics.
- Projections après 1, 3, 5 et 10 corrections.
- Explication automatique de la stabilité du score.
- Entity Noise V1 pour séparer compteurs bruts et causes actionnables.
- Maintenance Intelligence V1.
- Security Posture V1.
- Automation Reliability V1.
- Doctor Modes V1 : sécurité, automations, intégrations externes, maintenance, performance.
- Diagnostic Coverage V1.
- Scan Limitations V1.

## Contrats et qualité

- Verdict `action_required` distinct de `critical`.
- Self-Check V2 contrôle la cohérence version/schéma, les IDs, le triage, les paires de contrôleurs, la résilience, les projections, le bruit, la confidentialité et le contrat de partage.
- Le self-check vérifie explicitement qu'un SPOF réellement non protégé n'est pas masqué par une dépendance seulement faiblement protégée.
- Contrat d'export centralisé : `ha-doctor-share/4`, cible 28 Ko, plafond 32 Ko.
- `share_schema` et `export_meta` utilisent désormais la même source de vérité.
- Scan Performance V1 expose les temps par phase.
- Release Readiness V2 / Quality Gates V8.

## Interface et API

- Bloc Engine Candidate 0.10 dans Overview.
- Projections 1/3/5 corrections.
- Répartition des niveaux de preuve.
- Couverture diagnostic.
- Bruit unavailable/unknown compacté.
- Actions expliquées avec risque, preuve, sécurité de réparation et gain.
- Endpoint `/api/intelligence`.
- Endpoint `/api/scan-performance`.
- Share Report V4 et résumé Markdown enrichi.

## Invariants

- Lecture seule.
- Aucun auto-fix.
- Aucun redémarrage automatique.
- Aucun secret brut dans les rapports.
- Aucun état brut persisté.
- Aucun YAML brut persisté par la couche 0.10.
- Score V4 historique inchangé ; Score V5 reste une preview.
