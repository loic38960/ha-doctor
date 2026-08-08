# Changelog

## 0.2.0

- Résolution des automations basées sur des blueprints et des références `!input`.
- Analyse des packages Home Assistant.
- Détection des actions consécutives strictement identiques.
- Détection des IDs et alias d'automatisations dupliqués.
- Détection de boucles potentielles entre triggers et entités commandées.
- Détection des `time_pattern` très fréquents.
- Analyse des délais et timeouts de `wait_template` / `wait_for_trigger`.
- Conflits multi-automations plus intelligents grâce aux conditions d'état mutuellement exclusives.
- Nouveaux domaines de score Sécurité et Performances.
- Contrôles de base `trusted_proxies` et Recorder.
- Réduction des faux positifs provenant des valeurs par défaut des blueprints non utilisés.

## 0.1.0

- Première version alpha.
- Scanner read-only.
- API Home Assistant + informations Supervisor.
- Analyse YAML, états, automations et dépendances.
- Score de santé et export JSON.
