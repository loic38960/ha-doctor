# HA Doctor

HA Doctor est un prototype commercial d'audit **local et en lecture seule** pour Home Assistant OS.

## Alpha 0.2

- Interface via Home Assistant Ingress
- Inventaire Home Assistant via API REST
- Scan local des YAML sans lire `secrets.yaml`
- Détection d'entités `unavailable` / `unknown`
- Analyse des packages et des `!include`
- Résolution des automations utilisant des blueprints locaux
- Résolution des entrées `!input` des blueprints
- Détection des références d'entités absentes
- Détection des automatisations contrôlant la même entité
- Réduction des faux positifs lorsque les contrôleurs sont mutuellement exclusifs par une condition d'état
- Détection d'actions consécutives identiques
- Détection d'IDs et alias d'automatisations dupliqués
- Détection de boucles potentielles trigger → entité commandée
- Détection de `time_pattern` excessivement fréquents
- Détection de longues attentes en `mode: single`
- Contrôles Recorder et sécurité HTTP de base
- Détection heuristique de secrets potentiellement écrits en clair
- Graphe automation → triggers → entités commandées
- Scores Système / Entités / Automatisations / Configuration / Sécurité / Performances
- Rapport JSON téléchargeable
- **Aucune correction automatique en Alpha 0.2**

## Installation de développement

Le dépôt est privé pendant l'alpha. Pour le tester, utilisez le mode **App locale** recommandé par Home Assistant :

1. Copier le dossier `ha_doctor` dans `/addons/ha_doctor` sur Home Assistant OS.
2. Aller dans **Paramètres → Apps → App Store** et recharger la liste.
3. Installer l'App locale **HA Doctor**.
4. Démarrer l'App.
5. Cliquer sur **Ouvrir l'interface Web**.

Le dépôt de distribution public et les images précompilées seront créés avant la bêta publique.

## Sécurité

HA Doctor monte la configuration Home Assistant en lecture seule. `secrets.yaml`, `.storage`, les bases de données, certificats, clés, sauvegardes et archives sont exclus du scanner.

Le rapport ne conserve pas les valeurs brutes des états Home Assistant et ne conserve jamais la valeur d'un secret détecté.
