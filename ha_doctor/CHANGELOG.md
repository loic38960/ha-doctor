# Changelog

## 0.5.0

- Ajout du moteur explicatif local `explain_v1`, sans IA externe et sans envoi de données hors de Home Assistant.
- Chaque finding important reçoit désormais : diagnostic probable, niveau de confiance, impact, causes plausibles, preuves compactes, contrôles ordonnés, objectif de résolution et conditions permettant de relativiser l'alerte.
- Nouveau bloc `executive_summary` pour fournir un verdict lisible sans parcourir le JSON.
- Nouveau bloc `action_plan` qui fusionne les règles statiques et les causes racines du registre dans un ordre de traitement unique.
- Nouveau bloc `diagnostic_explanations` destiné à l'interface et à de futurs rapports avancés.
- Nouveau bloc `registry_observations` pour conserver les états potentiellement transitoires sans les transformer en panne.
- Corrélation des anomalies par intégration : une intégration entièrement indisponible devient une cause racine au lieu d'une série d'entités indépendantes.
- Corrélation par appareil : un appareil entièrement indisponible peut être diagnostiqué comme incident local lorsque son intégration reste globalement fonctionnelle.
- Détection de groupes de plusieurs appareils hors ligne appartenant à une même intégration lorsque cela apporte une cause commune plausible.
- Calibration spécifique des intégrations transitoires héritée de 0.4.1 : Tesla Fleet et Mobile App restent tolérées lorsque les valeurs peuvent dépendre de la veille ou de la remontée du terminal.
- Refonte complète de l'interface : Verdict HA Doctor → Plan d'action → Causes racines → Observations tolérées → Santé des entités → Findings techniques.
- Affichage du niveau de confiance directement dans les cartes de diagnostic.
- Le moteur explicatif n'applique aucune correction et n'utilise jamais une valeur brute de secret comme preuve.
- Le score reste volontairement inchangé : `explanatory_scoring: false` pendant la validation Alpha.
- Ajout de tests de non-régression sur SmartThings, Tesla, MQTT, secrets et ordre du plan d'action.

## 0.4.1

- Calibration des groupes Tesla Fleet : un grand nombre de valeurs `unknown` sans état manquant ne suffit plus à déclarer le véhicule hors ligne.
- Calibration de Mobile App afin de limiter les faux diagnostics lorsque des capteurs du terminal ne remontent pas temporairement de données.
- Les entités dérivées de l'intégration `energy` sont classées secondaires et ne simulent plus une panne d'intégration.
- Séparation stricte entre `probable_orphan_count` et `review_candidate_count`.
- `HD-REG-001` est réservé aux entrées de registre actives sans aucun état correspondant.
- Nouvelle règle `HD-REG-002` pour les entités locales simplement `unavailable` sans preuve d'orphelin.
- Ajout des compteurs `problematic` pour distinguer les groupes réellement hors ligne/dégradés des simples groupes à surveiller.

## 0.4.0

- Analyse read-only des registres Home Assistant via le proxy WebSocket officiel du Supervisor, sans lecture de `.storage`.
- Regroupement des entités problématiques par intégration (`platform`) afin d'identifier les pannes communes au lieu de compter chaque entité séparément.
- Regroupement par appareil à partir du Device Registry avec état `Hors ligne`, `Dégradé`, `À surveiller` ou `Secondaire`.
- Les entités `config`, `diagnostic`, boutons, mises à jour et autres fonctions secondaires sont distinguées des entités principales dans le calcul de santé des groupes.
- Première détection d'entités probablement orphelines : entrées locales actives du registre sans état, ou entités locales indisponibles sans appareil associé.
- Les candidats orphelins sont classés par confiance et ne déclenchent jamais de suppression automatique.
- Nouveau finding `HD-REG-001` classé `À vérifier` lorsque des candidats orphelins existent.
- Nouvelle section d'interface `Intégrations & appareils` et liste des candidats orphelins.
- Le score 0.3.2 est volontairement conservé : les nouveaux diagnostics de registre sont en preview et ne sont pas encore scorés.
- Aucun payload brut du registre ni token Supervisor n'est persisté dans le rapport.
- Fallback gracieux : si le WebSocket/registre est indisponible, le diagnostic YAML/états continue normalement.

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
