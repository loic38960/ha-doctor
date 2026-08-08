# Changelog

## 0.7.0

- Nouvelle architecture de diagnostic `root_cause_temporal_v4` et **Score V4**.
- Le score est calculé après corrélation des causes racines, déduplication du bruit et analyse de dépendances.
- Ajout de plafonds de pénalité par domaine afin d'éviter de compter plusieurs fois les symptômes d'une même panne.
- Le volume brut des entités `unavailable` / `unknown` reste informatif et n'est pas scoré directement lorsqu'une cause racine l'explique.
- Nouveau graphe `entity_graph_v2` distinguant triggers, commandes, lectures et appels de services Home Assistant.
- Les appels tels que `switch.turn_on`, `input_number.set_value`, `climate.set_temperature` et `todo.get_items` ne sont plus traités comme des entités.
- Nouveau calcul de blast radius pondéré : les actionneurs et capteurs métier pèsent davantage que les helpers de coordination.
- Les fan-outs de `input_boolean`, `input_number`, `input_datetime`, `counter` et autres helpers sont fortement décotés dans le calcul de criticité.
- Chaque diagnostic expose maintenant les automatisations réellement critiques, les dépendances helper-only et un score d'impact pondéré.
- Nouveau bloc `architecture_analysis` : complexité, hotspots d'entités, actionneurs partagés, helper hubs, trigger hubs, boucles de contrôle et profils d'automatisations complexes.
- Nouveau bloc `regression_analysis` avec état `stable`, `improved` ou `degraded`, variation de score, nouveaux diagnostics et diagnostics résolus.
- Historique temporel V2 compatible avec les snapshots V3 de la 0.6.
- Les nouveaux diagnostics ont désormais un `first_seen` explicite au lieu de `null`.
- Nouveau bloc `maintenance_debt` indépendant de l'indice de santé : références absentes, candidats locaux, orphelins, archives et couverture YAML.
- Nouveau système de `quality_gates` pour vérifier API, parsing YAML, blueprints, registres, confidentialité, graphe et cohérence interne du rapport.
- Correction de l'incohérence possible entre `diagnostic_summary` et `action_plan` : le résumé est reconstruit depuis le plan corrélé final.
- Nouveau champ `why_now` dans le plan d'action pour expliquer la priorité de traitement.
- Nouveau bloc `recommendation_queue` présentant les premières actions recommandées.
- Nouveau schéma explicite `ha-doctor-report/0.7` et bloc `report_schema`.
- Nouveaux endpoints `/api/version`, `/api/insights`, `/api/actions`, `/api/architecture`, `/api/quality` et `/api/diagnostic?id=...`.
- `/api/history` accepte les anciens scores V3 et expose les métriques V4 disponibles.
- Export anonymisé enrichi avec score V4, architecture, régression, dette de maintenance et quality gates sous forme agrégée uniquement.
- Refonte majeure de l'interface en six vues : Vue d'ensemble, Plan d'action, Architecture, Intégrations & appareils, Historique, Qualité & confidentialité.
- Le plan d'action dispose maintenant de filtres texte, priorité, domaine et confiance.
- Nouvelle vue Architecture avec hotspots et automatisations les plus interconnectées.
- Nouvelle vue Historique avec courbe du score et diagnostics nouveaux/persistants/résolus.
- Nouvelle vue Qualité & confidentialité avec quality gates et indicateur de dette de maintenance.
- Renforcement du packaging Docker : tous les modules Python du contexte App sont copiés automatiquement via `COPY *.py ./`.
- Ajout de smoke tests sur l'image Docker réelle pour vérifier la présence et l'import de `scanner_v070`, `intelligence_v070`, `share_export` et `app`.
- Ajout de tests de non-régression spécifiques au filtrage des services, à la pondération helper/actionneur, au score indépendant des volumes bruts, à la migration temporelle, à l'anonymisation et à la cohérence du rapport.
- La CI construit désormais l'image Home Assistant App réelle et vérifie ses modules et assets avant validation.
- Toujours aucune IA externe, aucun auto-fix et aucune modification automatique de Home Assistant.

## 0.6.0

- Nouveau score `root_cause_temporal_v1` calculé après corrélation des causes racines.
- Les volumes bruts `unavailable` / `unknown` ne sont plus pénalisés une seconde fois lorsqu'une cause racine explique déjà ces entités.
- Le score V3 tient compte de la priorité, de la sévérité, de la confiance, de la persistance temporelle et de l'impact sur les automatisations.
- Ajout d'un historique local des 20 derniers scans dans `/data/ha-doctor-history.json`.
- L'historique conserve uniquement dates, scores, compteurs et identifiants de diagnostics ; aucun état brut ni secret n'est persisté.
- Les incidents de registre ponctuels sont moins pénalisés au premier scan puis renforcés lorsqu'ils persistent.
- Détection des diagnostics nouveaux, persistants et résolus depuis le scan précédent.
- Ajout de l'analyse des dépendances : HA Doctor relie les entités d'un diagnostic aux automatisations qui les utilisent.
- Chaque action expose désormais un niveau d'impact de dépendance et le nombre d'automatisations concernées.
- Correction de l'incohérence du résumé exécutif 0.5 : les nombres d'intégrations/appareils affichés proviennent désormais des incidents réellement retenus après calibration.
- Le plan d'action n'est plus tronqué silencieusement : `total`, `displayed` et `remaining` sont explicites et toutes les actions retenues sont exposées.
- `HD-ENT-001` et `HD-ENT-003` restent visibles dans les findings techniques mais sont retirées du plan lorsque des causes racines de registre expliquent déjà le volume.
- `HD-REG-002` de faible confiance est retirée du plan lorsqu'aucun orphelin probable n'est détecté.
- Nouveau bloc `root_cause_summary` avec le nombre d'incidents d'intégration, d'appareil et de cluster réellement retenus.
- Nouveau bloc `temporal_analysis` avec évolution du score, persistance et résolutions.
- Nouveau moteur `explain_v2_temporal` et calibration `root_cause_v2`.
- Nouveau endpoint `/api/history` fournissant uniquement un historique agrégé.
- Nouveau export `ha-doctor-anonymized.json` qui retire entity_id, noms d'appareils, intégrations, automatisations et chemins de fichiers.
- Le résumé compact est désormais explicitement marqué comme non anonymisé.
- Refonte de l'interface : score V3, évolution dans le temps, plan corrélé, dépendances et export anonymisé.
- Ajout de tests de non-régression sur la persistance, la déduplication du bruit, l'impact des dépendances et l'anonymisation.

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
