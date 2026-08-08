# HA Doctor

HA Doctor est un prototype d'audit **en lecture seule** pour Home Assistant OS.

## V0.1

- Interface via Home Assistant Ingress
- Inventaire Home Assistant via API REST
- Scan local des YAML sans lire `secrets.yaml`
- Détection d'entités `unavailable` / `unknown`
- Détection de références d'entités YAML absentes de l'état courant
- Analyse des automations (modes, délais longs, entités contrôlées par plusieurs automations)
- Détection heuristique de secrets potentiellement écrits en clair
- Graphe simplifié des dépendances automation → entité
- Score par domaine et score global
- Rapport JSON téléchargeable
- **Aucune correction automatique en V0.1**

## Installation de développement

1. Ajouter `https://github.com/loic38960/-ha-doctor` comme dépôt d'Apps tiers dans Home Assistant.
2. Recharger l'App Store.
3. Installer **HA Doctor**.
4. Démarrer l'App.
5. Cliquer sur **Ouvrir l'interface Web**.

## Sécurité

HA Doctor V0.1 monte la configuration Home Assistant en lecture seule. Le scanner exclut explicitement `secrets.yaml`, les fichiers de base de données, les certificats, les sauvegardes et les fichiers sensibles de `.storage`.
