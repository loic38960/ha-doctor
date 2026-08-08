# HA Doctor

HA Doctor est un prototype commercial d'audit **local et en lecture seule** pour Home Assistant OS.

## Alpha 0.3

- Interface via Home Assistant Ingress
- Inventaire Home Assistant via API REST
- Scan local des YAML sans lire `secrets.yaml`
- Diagnostic priorisé : **À corriger maintenant / À vérifier / Optimisations / Informations**
- Regroupement intelligent des entités `unavailable` et `unknown`
- Score de santé Alpha recalibré selon la priorité des anomalies
- Conservation de l'ancien modèle de score pour comparaison pendant l'Alpha
- Analyse des packages, `!include`, blueprints et entrées `!input`
- Détection des références d'entités absentes avec filtrage des services/actions Home Assistant
- Détection des automatisations contrôlant la même entité
- Réduction des faux positifs lorsque les contrôleurs sont mutuellement exclus par une condition d'état
- Détection d'actions consécutives identiques
- Détection d'IDs et alias d'automatisations dupliqués
- Détection de boucles potentielles trigger → entité commandée
- Détection de `time_pattern` excessivement fréquents
- Détection de longues attentes en `mode: single`
- Détection de plusieurs automations écrivant dans les mêmes compteurs numériques
- Détection d'un capteur Integral alimenté par une source non numérique
- Contrôles Recorder et sécurité HTTP de base
- Détection heuristique de secrets potentiellement écrits en clair
- Graphe automation → triggers → entités commandées
- Scores Système / Entités / Automatisations / Configuration / Sécurité / Performances
- Rapport JSON téléchargeable et partageable
- **Aucune correction automatique en Alpha 0.3**

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

Le rapport ne conserve pas les valeurs brutes des états Home Assistant, ne conserve jamais la valeur d'un secret détecté et retire les identifiants locaux inutiles tels que `location_name` et `hostname`.

## Développement

Les tests unitaires et la compilation Python sont exécutés automatiquement par GitHub Actions sur `main` et sur les pull requests.
