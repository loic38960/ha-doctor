# HA Doctor 0.2.0 Alpha

## Fonctionnement

HA Doctor effectue un audit local en lecture seule. Cette version ne corrige, ne supprime, ne redémarre et ne modifie rien dans Home Assistant.

## Données lues

- API Home Assistant : configuration générale et états courants.
- API Supervisor : informations générales accessibles au rôle `default`.
- `/ha_config` : fichiers YAML autorisés, montés en lecture seule.

## Fichiers explicitement ignorés

- `secrets.yaml` / `secrets.yml`
- l'intégralité de `.storage`
- bases SQLite (`*.db`, `*.sqlite*`)
- certificats et clés (`*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`)
- sauvegardes et archives

## Analyse des blueprints

HA Doctor 0.2 charge les blueprints présents dans `blueprints/automation`, applique les valeurs fournies via `use_blueprint.input` et résout les références `!input`. Cela permet d'analyser les entités réellement utilisées par chaque instance de blueprint.

Les valeurs par défaut présentes dans un blueprint non utilisé ne sont pas considérées comme des références actives.

## Résultats

L'interface affiche :

- score global
- scores Système / Entités / Automatisations / Configuration / Sécurité / Performances
- problèmes Critique / Élevé / Moyen / Faible / Information
- dépendances détectées
- téléchargement du rapport JSON

## Limitations Alpha 0.2

- Certaines références construites entièrement dynamiquement en Jinja ne peuvent pas être résolues statiquement.
- Les conflits entre automations sont une analyse prudente : HA Doctor sait reconnaître certaines exclusions par condition `state`, mais pas encore toutes les exclusions exprimées en templates Jinja.
- Le scanner n'analyse pas encore Zigbee2MQTT, ZHA, MQTT et les sauvegardes avec des règles dédiées.
- Un diagnostic reste une aide à la décision et ne remplace pas la validation humaine avant modification.
