# Changelog

## 0.3.2

- Correction du triage des entités `notify.*` en état `unknown` : elles sont désormais exclues comme entités stateless avant le regroupement.
- Correction spécifique des `notify` mobiles dont le nom contient `iphone` ou `ipad` et qui étaient auparavant classés à tort dans `Mobiles / Companion App`.
- Modèle de score/triage identifié comme `priority_v1.2` sans changement des pénalités ni des priorités de diagnostic.
- Ajout de tests de non-régression sur ce cas réel.

## 0.3.1

- Raffinement du triage des entités indisponibles/inconnues.
- Séparation des groupes probablement transitoires, optionnels/secondaires et réellement à examiner.
- Libellés moins alarmistes pour les entités `unavailable`.
- Version de l'App injectée automatiquement dans l'interface pour éviter les numéros affichés en dur.

## 0.3.0

- Nouveau diagnostic orienté utilisateur : `À corriger maintenant`, `À vérifier`, `Optimisations`, `Informations`.
- Nouveau modèle de score `priority_v1`, moins sensible au volume brut d'alertes génériques.
- Conservation de l'ancien score dans `score_meta.legacy_global` pour suivre l'évolution du modèle Alpha.
- Regroupement des entités `unavailable` et `unknown` par familles : mobiles, paramètres d'appareils, présence, capteurs, actionneurs, etc.
- Distinction entre entités probablement temporaires/optionnelles et entités à examiner.
- Filtrage des références uniquement présentes dans `recorder.exclude.entities`.
- Utilisation de la liste réelle des services Home Assistant pour éviter de confondre actions et `entity_id`.
- Nouveau résumé `diagnostic_summary` directement exploitable par l'interface ou un futur rapport PDF.
- Nouvelle interface centrée sur le plan d'action plutôt que sur les règles techniques.
- Les identifiants `location_name` et `hostname` restent retirés du rapport partageable.

## 0.2.4

- Validation des références à partir du registre réel des services Home Assistant.
- Filtrage supplémentaire des références techniques et blueprints.
- Détection `HD-CFG-006` des capteurs Integral alimentés par une source non numérique.
- Retrait de `location_name` et `hostname` du JSON exporté.

## 0.2.3

- Réduction importante des faux positifs de références YAML.
- Séparation des secrets actifs et des secrets présents dans des archives/sauvegardes.
- Nouvelle règle `HD-AUTO-009` pour les automatisations qui écrivent simultanément les mêmes compteurs numériques.
- Meilleure gestion des conflits impliquant scripts, scènes et helpers.
- Filtrage d'une partie des entités stateless en état `unknown`.

## 0.2.2

- Ajout d'un statut d'analyse en cours dans l'interface.
- Bouton de scan désactivé pendant une analyse et rafraîchissement automatique à la fin.

## 0.2.1

- Correction du démarrage avec l'image de base Home Assistant/S6 : ajout de `init: false` requis par S6 Overlay v3.
- Logs de démarrage explicites et sortie Python non bufferisée pour faciliter le diagnostic.
- Mise à jour de l'URL du dépôt après renommage en `loic38960/ha-doctor`.

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
