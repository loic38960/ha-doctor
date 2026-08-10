# HA Doctor 0.8.4 — Semantic Lineage

## Objectif

0.8.4 consolide les moteurs introduits en 0.8.x sans modifier automatiquement Home Assistant et sans appliquer le Score V5 au score principal.

## Nouveautés

- **Flow Confidence V3.1** : synchronisation des compteurs de confiance du graphe après promotion des cibles dynamiques confirmées.
- **Architecture V3 post-Flow** : recalcul complet des hotspots et risques après la résolution finale des cibles dynamiques.
- **Controller Protocols V1** : détection prudente des handoffs de phase entre automatisations lorsque la coordination passe par un helper et des transitions d'état différentes.
- **Entity Lineage V1** : graphe conservateur `source -> entité template dérivée -> automatisation` pour relier une panne d'intégration aux usages indirects.
- **Registry Blast Radius V4** : corrélation directe et indirecte des incidents d'intégration/appareil avec les automatisations impactées.
- **Temporal V3.1** : séparation entre historique du plan d'action et historique de tous les diagnostics.
- **Résolution vs déclassement** : un diagnostic toujours détecté mais retiré du plan est maintenant `deescalated`, pas `resolved`.
- **Resilience Recommendations V1** : une dépendance externe très critique avec des automations non protégées devient une recommandation concrète du plan d'action, sans pénalité de score supplémentaire.
- **Consistency Gates V4** : le rapport échoue si Flow et ses métadonnées divergent, si l'architecture n'a pas été recalculée après Flow, si un diagnostic déclaré résolu existe encore, ou si les invariants de confidentialité du lineage sont violés.
- **Quality Gates V4** : ajout de gates dédiés au lineage et à la sémantique temporelle.
- Nouveau endpoint local read-only : `/api/semantic-lineage`.

## Confidentialité

- `secrets.yaml` reste exclu du scan.
- `.storage`, backups, certificats et clés ne sont pas lus par le moteur de lineage.
- Le lineage ne persiste ni YAML brut, ni texte de template brut, ni état brut, ni valeur de secret.
- Aucun auto-fix, redémarrage, suppression ou modification de configuration.

## Compatibilité

Schéma : `ha-doctor-report/0.8.4`.

Compatible avec les rapports 0.5, 0.6, 0.7, 0.8, 0.8.1, 0.8.2 et 0.8.3.

Le **Score V4** reste le score principal pour préserver la continuité de l'historique. Le Score V5 reste un preview.
