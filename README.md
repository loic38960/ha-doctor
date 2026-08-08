# HA Doctor

HA Doctor est un prototype commercial de diagnostic **local, explicatif et en lecture seule** pour Home Assistant OS.

## Alpha 0.5

### Diagnostic utilisateur

- Interface via Home Assistant Ingress entièrement recentrée sur le **verdict** et le **plan d'action**.
- Diagnostic priorisé : **À corriger maintenant / À vérifier / Optimisations / Informations**.
- Nouveau moteur local `explain_v1` : aucune IA externe et aucun coût de tokens.
- Pour chaque diagnostic important :
  - cause probable ;
  - niveau de confiance ;
  - impact ;
  - preuves utilisées ;
  - causes alternatives ;
  - contrôles ordonnés ;
  - objectif de résolution ;
  - cas où l'alerte peut être relativisée.
- Nouveau `executive_summary` destiné à expliquer le rapport sans lire le JSON.
- Nouveau `action_plan` combinant règles YAML, sécurité, intégrations et appareils.
- Corrélation des pannes par cause racine afin de ne pas compter plusieurs entités d'un même appareil comme plusieurs incidents.
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
- Regroupement intelligent des entités `unavailable` et `unknown`.
- Analyse des packages, `!include`, blueprints et entrées `!input`.
- Détection des références d'entités absentes avec filtrage des services/actions Home Assistant.
- Détection des automatisations contrôlant la même entité.
- Réduction des faux positifs lorsque les contrôleurs sont mutuellement exclus par une condition d'état.
- Détection d'actions consécutives identiques.
- Détection d'IDs et alias d'automatisations dupliqués.
- Détection de boucles potentielles trigger → entité commandée.
- Détection de `time_pattern` excessivement fréquents.
- Détection de longues attentes en `mode: single`.
- Détection de plusieurs automations écrivant dans les mêmes compteurs numériques.
- Détection d'un capteur Integral alimenté par une source non numérique.
- Contrôles Recorder et sécurité HTTP de base.
- Détection heuristique de secrets potentiellement écrits en clair.
- Graphe automation → triggers → entités commandées.
- Scores Système / Entités / Automatisations / Configuration / Sécurité / Performances.
- Rapport JSON téléchargeable et partageable.

### Score Alpha

La couche explicative 0.5 et les causes racines du registre **ne modifient pas encore le score**. L'indice reste comparable aux rapports 0.4.x pendant la phase de validation sur des installations réelles.

**Aucune correction automatique en Alpha 0.5.**

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

Le rapport ne conserve pas les valeurs brutes des états Home Assistant, ne conserve jamais la valeur d'un secret détecté et retire les identifiants locaux inutiles tels que `location_name` et `hostname`.

Le moteur d'explication 0.5 travaille exclusivement à partir du rapport déjà redacted : `external_ai_used: false`, `automatic_fix: false`, `read_only: true`.

## Développement

Les tests unitaires, la compilation Python et la construction réelle de l'image Home Assistant App sont exécutés automatiquement par GitHub Actions sur `main` et sur les pull requests.
