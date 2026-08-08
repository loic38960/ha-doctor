# HA Doctor 0.3.0 Alpha

## Fonctionnement

HA Doctor effectue un audit local en lecture seule. Il ne corrige, ne supprime, ne redémarre et ne modifie rien dans Home Assistant.

## Données lues

- API Home Assistant : configuration générale, états courants et liste des services/actions disponibles.
- API Supervisor : informations générales accessibles au rôle `default`.
- `/ha_config` : fichiers YAML autorisés, montés en lecture seule.

Les états bruts servent uniquement pendant l'analyse et ne sont pas persistés dans le rapport.

## Fichiers explicitement ignorés

- `secrets.yaml` / `secrets.yml`
- l'intégralité de `.storage`
- bases SQLite (`*.db`, `*.sqlite*`)
- certificats et clés (`*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`)
- sauvegardes binaires et archives

Les anciens YAML d'archive peuvent être parcourus uniquement pour détecter la présence potentielle de secrets, sans enregistrer leur valeur.

## Diagnostic 0.3

Chaque finding technique est associé à une priorité utilisateur :

- `À corriger maintenant` : risque ou erreur suffisamment probable pour être traité en priorité.
- `À vérifier` : anomalie crédible mais nécessitant une validation du contexte.
- `Optimisations` : dette technique, robustesse ou amélioration de maintenance.
- `Informations` : contexte du scan, couverture et éléments non bloquants.

Le JSON expose `diagnostic_summary`, `priority`, `priority_label` et `entity_health` pour permettre une future génération de rapport PDF ou une analyse IA.

## Santé des entités

HA Doctor regroupe les entités `unavailable` et `unknown` en familles :

- Mobiles / Companion App
- Paramètres d'appareils
- Présence / localisation
- Capteurs
- Appareils / actionneurs
- autres domaines

Les entités stateless connues (`scene`, `button`, `event`, `stt`, etc.) ne sont pas comptées comme `unknown` problématiques.

## Score Alpha

La version 0.3 utilise le modèle `priority_v1` : les alertes générales pénalisent moins le score, tandis que les anomalies fortes restent prioritaires.

Le précédent score est conservé dans `score_meta.legacy_global` afin de comparer les modèles pendant la phase Alpha. Le score reste un indice d'aide à la décision, pas une certification.

## Analyse des blueprints

HA Doctor charge les blueprints présents dans `blueprints/automation`, applique les valeurs fournies via `use_blueprint.input` et résout les références `!input`. Les valeurs par défaut présentes dans un blueprint non utilisé ne sont pas considérées comme des références actives.

## Limitations Alpha 0.3

- Certaines références construites entièrement dynamiquement en Jinja ne peuvent pas être résolues statiquement.
- Les conflits entre automatisations restent une analyse prudente : certaines exclusions exprimées en templates Jinja ne sont pas encore comprises.
- Le regroupement des entités indisponibles/inconnues est heuristique et sera enrichi avec les intégrations et appareils réels.
- Le scanner n'analyse pas encore Zigbee2MQTT, ZHA, MQTT, les sauvegardes et les logs avec des règles dédiées profondes.
- Toute modification de Home Assistant doit être validée humainement avant application.
