# HA Doctor 0.1.0

## Fonctionnement

HA Doctor effectue un audit local en lecture seule. Cette version ne corrige, ne supprime, ne redémarre et ne modifie rien dans Home Assistant.

## Données lues

- API Home Assistant : configuration générale et états courants.
- API Supervisor : informations générales accessibles au rôle `default`.
- `/ha_config` : fichiers YAML autorisés, montés en lecture seule.

## Fichiers explicitement ignorés

- `secrets.yaml`
- `.storage/auth*`
- `.storage/onboarding`
- bases SQLite (`*.db`, `*.sqlite*`)
- certificats et clés (`*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`)
- sauvegardes et archives

## Résultats

L'interface affiche :

- score global
- scores Système / Entités / Automatisations / Configuration
- problèmes Critique / Élevé / Moyen / Faible / Information
- dépendances détectées
- téléchargement du rapport JSON

## Limitations V0.1

- Les références dynamiques créées par templates Jinja peuvent provoquer des faux positifs.
- Le scanner n'analyse pas encore les registres internes complets de Home Assistant.
- Zigbee2MQTT, ZHA, MQTT, Recorder et sauvegardes auront des règles dédiées dans les versions suivantes.
