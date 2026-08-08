# HA Doctor

HA Doctor est un prototype commercial de diagnostic **local, explicatif et en lecture seule** pour Home Assistant OS.

## Alpha 0.6

### Contrôle technique orienté causes racines

- Nouveau **score V3** calculé à partir des diagnostics corrélés plutôt qu'à partir du volume brut d'entités `unavailable` / `unknown`.
- Le score tient compte de la **priorité**, de la **sévérité**, de la **confiance**, de la **persistance dans le temps** et de l'**impact sur les automatisations**.
- Les alertes génériques sur le volume d'entités sont conservées comme métriques techniques mais retirées du plan d'action lorsqu'une cause racine explique déjà le problème.
- Les compteurs affichés dans le résumé exécutif proviennent désormais des incidents réellement retenus après calibration, et non des compteurs bruts du registre.
- Le plan d'action expose toutes les actions retenues avec `total`, `displayed`, `remaining` et la liste des alertes volontairement supprimées comme bruit.

### Historique local

- Conservation des **20 derniers scans** dans `/data/ha-doctor-history.json`.
- L'historique ne stocke que : date, score, compteurs, identifiants de diagnostics actifs et nombre d'incidents de registre.
- Aucun état brut Home Assistant, aucune valeur de secret et aucun payload brut du registre ne sont stockés dans l'historique.
- Un incident de registre ponctuel est moins pénalisé lors de sa première apparition ; la confiance augmente lorsqu'il persiste sur plusieurs scans.
- Détection des diagnostics nouveaux, persistants et résolus depuis le scan précédent.

### Impact sur les dépendances

- Chaque diagnostic tente d'identifier les automatisations qui référencent les entités concernées.
- Le rapport expose le nombre d'automatisations impactées et distingue un impact faible, moyen ou élevé.
- L'impact de dépendance intervient dans le score V3 afin qu'une panne réellement utilisée par la logique Home Assistant pèse plus lourd qu'une entité isolée sans dépendance détectée.

### Export anonymisé

- Nouveau bouton **Rapport anonymisé**.
- L'export anonymisé retire les `entity_id`, noms d'appareils, noms d'intégrations, noms d'automatisations et chemins de fichiers.
- Le rapport complet reste disponible localement pour le diagnostic détaillé.
- Le résumé compact est explicitement distingué de l'export anonymisé : compact ne signifie pas anonyme.

### Diagnostic utilisateur

- Interface via Home Assistant Ingress centrée sur le **Verdict HA Doctor**, l'**évolution dans le temps**, le **plan d'action corrélé**, les **causes racines** et les **mesures brutes**.
- Diagnostic priorisé : **À corriger maintenant / À vérifier / Optimisations / Informations**.
- Moteur local déterministe : aucune IA externe et aucun coût de tokens.
- Pour chaque diagnostic important : cause probable, niveau de confiance, impact, preuves utilisées, causes alternatives, contrôles ordonnés et objectif de résolution.
- Corrélation des pannes par intégration, groupe d'appareils et appareil individuel.
- Distinction explicite entre pannes probables et observations transitoires telles que Tesla Fleet ou Mobile App.

### Analyse Home Assistant

- Inventaire Home Assistant via API REST.
- Scan local des YAML sans lire `secrets.yaml`.
- Analyse read-only des registres Home Assistant via le proxy WebSocket officiel du Supervisor.
- Regroupement des problèmes par **intégration** et par **appareil**.
- Distinction entre entités principales et fonctions secondaires/configuration/diagnostic.
- Calibration des intégrations transitoires : Tesla Fleet et Mobile App ne sont pas déclarées hors ligne uniquement sur un grand nombre de valeurs `unknown`/`unavailable`.
- Séparation entre vrais **orphelins probables** et simples entités locales `unavailable` à revoir.
- Aucun accès direct à `.storage`.
- Analyse des packages, `!include`, blueprints et entrées `!input`.
- Détection des références d'entités absentes avec filtrage des services/actions Home Assistant.
- Détection des automatisations contrôlant la même entité.
- Réduction des faux positifs lorsque les contrôleurs sont mutuellement exclus par une condition d'état.
- Détection d'actions consécutives identiques, IDs/alias dupliqués, boucles potentielles, `time_pattern` fréquents, longues attentes `mode: single`, doubles écritures de compteurs numériques et capteurs Integral incompatibles.
- Contrôles Recorder et sécurité HTTP de base.
- Détection heuristique de secrets potentiellement écrits en clair.
- Graphe automation → triggers → entités commandées.

**Aucune correction automatique en Alpha 0.6.**

## Installation via dépôt personnalisé

Dans Home Assistant :

1. Ouvrir **Paramètres → Apps → App Store**.
2. Ouvrir le menu **⋮ → Dépôts**.
3. Ajouter `https://github.com/loic38960/ha-doctor`.
4. Rechercher les mises à jour de l'App Store.
5. Installer ou mettre à jour **HA Doctor**.
6. Démarrer l'App et ouvrir son interface Web.

## Sécurité

HA Doctor monte la configuration Home Assistant en lecture seule. `secrets.yaml`, `.storage`, les bases de données, certificats, clés et sauvegardes binaires sont exclus du scanner.

La couche registre utilise uniquement le WebSocket Home Assistant via le Supervisor. Le payload brut des registres et le token Supervisor ne sont jamais enregistrés dans le rapport.

Le rapport complet ne conserve pas les valeurs brutes des états Home Assistant et ne conserve jamais la valeur d'un secret détecté. L'historique temporel stocke uniquement des métadonnées de diagnostic.

Le moteur d'explication et de score travaille localement : `external_ai_used: false`, `automatic_fix: false`, `read_only: true`.

## Développement

Les tests unitaires, la compilation Python et la construction réelle de l'image Home Assistant App sont exécutés automatiquement par GitHub Actions sur `main` et sur les pull requests.
