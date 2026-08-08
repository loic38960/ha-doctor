# HA Doctor

HA Doctor est un prototype commercial d'audit **local et en lecture seule** pour Home Assistant OS.

## Alpha 0.4

- Interface via Home Assistant Ingress
- Inventaire Home Assistant via API REST
- Scan local des YAML sans lire `secrets.yaml`
- Diagnostic priorisé : **À corriger maintenant / À vérifier / Optimisations / Informations**
- Regroupement intelligent des entités `unavailable` et `unknown`
- Analyse read-only des registres Home Assistant via le proxy WebSocket officiel du Supervisor
- Regroupement des problèmes par **intégration** et par **appareil**
- Distinction entre entités principales et fonctions secondaires/configuration/diagnostic
- Détection preview d'entités **probablement orphelines** avec niveau de confiance
- Aucun accès direct à `.storage`
- Score de santé Alpha recalibré selon la priorité des anomalies
- Les nouveaux insights de registre 0.4 ne modifient pas encore le score afin d'être validés sur des installations réelles
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
- **Aucune correction automatique en Alpha 0.4**

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

La couche registre 0.4 utilise uniquement le WebSocket Home Assistant via le Supervisor. Le payload brut des registres et le token Supervisor ne sont jamais enregistrés dans le rapport.

Le rapport ne conserve pas les valeurs brutes des états Home Assistant, ne conserve jamais la valeur d'un secret détecté et retire les identifiants locaux inutiles tels que `location_name` et `hostname`.

## Développement

Les tests unitaires, la compilation Python et la construction réelle de l'image Home Assistant App sont exécutés automatiquement par GitHub Actions sur `main` et sur les pull requests.
