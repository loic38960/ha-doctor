# HA Doctor 0.5.0 Alpha

## Fonctionnement

HA Doctor effectue un diagnostic local en lecture seule. Il ne corrige, ne supprime, ne redémarre et ne modifie rien dans Home Assistant.

La chaîne 0.5 est organisée en couches :

1. collecte Home Assistant / Supervisor ;
2. analyse YAML et automatisations ;
3. triage des états `unavailable` / `unknown` ;
4. analyse des Entity Registry / Device Registry via WebSocket ;
5. calibration des cas transitoires ;
6. moteur explicatif local ;
7. plan d'action et interface utilisateur.

## Données lues

- API Home Assistant : configuration générale, états courants et liste des services/actions disponibles.
- API Supervisor : informations générales accessibles au rôle `default`.
- WebSocket Home Assistant via le proxy Supervisor : Entity Registry et Device Registry.
- `/ha_config` : fichiers YAML autorisés, montés en lecture seule.

Les états bruts servent uniquement pendant l'analyse et ne sont pas persistés dans le rapport. Les payloads bruts des registres et le token Supervisor ne sont pas persistés non plus.

## Fichiers explicitement ignorés

- `secrets.yaml` / `secrets.yml`
- l'intégralité de `.storage`
- bases SQLite (`*.db`, `*.sqlite*`)
- certificats et clés (`*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`)
- sauvegardes binaires et archives non YAML

Les anciens YAML d'archive peuvent être parcourus uniquement pour détecter la présence potentielle de secrets, sans enregistrer leur valeur.

## Priorités utilisateur

Chaque finding technique est associé à une priorité :

- `À corriger maintenant` : risque ou erreur suffisamment probable pour être traité en priorité.
- `À vérifier` : anomalie crédible mais nécessitant une validation du contexte.
- `Optimisations` : dette technique, robustesse ou amélioration de maintenance.
- `Informations` : contexte du scan, couverture et éléments non bloquants.

## Moteur explicatif 0.5

Le moteur `explain_v1` est **déterministe et local**. Il n'appelle aucun LLM ni service d'IA externe.

Pour chaque diagnostic, HA Doctor peut produire :

- `diagnosis` : interprétation du constat ;
- `confidence` / `confidence_score` : niveau de certitude ;
- `impact` : conséquence potentielle ;
- `probable_causes` : causes plausibles classées sans prétendre à une certitude absolue ;
- `evidence` : preuves compactes déjà présentes dans le rapport redacted ;
- `checks` : contrôles manuels ordonnés ;
- `resolution_goal` : état cible attendu ;
- `safe_to_ignore_when` : conditions dans lesquelles l'alerte peut être relativisée ;
- `automatic_fix: false` ;
- `read_only: true`.

Les preuves du moteur explicatif n'incluent jamais les valeurs de secrets. Les exemples sont limités à des métadonnées telles que fichier, ligne, clé, entity_id, alias ou groupe détecté.

## Corrélation des causes racines

La 0.5 ne se contente plus de compter des entités. Elle essaie de déterminer si plusieurs symptômes partagent une cause commune.

### Intégration entièrement indisponible

Si la quasi-totalité des entités principales d'une intégration est touchée et que plusieurs appareils suivent le même motif, HA Doctor crée un diagnostic au niveau de l'intégration au lieu de répéter les appareils individuellement.

### Appareil isolé hors ligne

Si toutes les entités principales d'un appareil sont touchées mais que l'intégration reste globalement saine, l'incident est attribué à l'appareil.

### Plusieurs appareils d'un même sous-ensemble

Lorsque plusieurs appareils distincts d'une intégration sont entièrement touchés alors que d'autres restent sains, HA Doctor peut créer un cluster de cause commune : passerelle, zone réseau/radio, ancienne association ou sous-ensemble volontairement hors tension.

### Cas transitoires

Tesla Fleet et Mobile App sont volontairement traités avec prudence. Un volume important de valeurs `unknown` ou de capteurs mobiles non remontés ne suffit pas à conclure à une panne.

Ces cas peuvent apparaître dans `registry_observations` plutôt que dans le plan d'action.

## Santé des entités

HA Doctor regroupe les entités `unavailable` et `unknown` en familles :

- Mobiles / Companion App
- Paramètres d'appareils
- Présence / localisation
- Capteurs
- Appareils / actionneurs
- mises à jour / fonctions secondaires
- autres domaines

Les entités stateless connues (`scene`, `button`, `event`, `stt`, etc.) sont filtrées autant que possible avant le triage `unknown`.

## Registres et orphelins

HA Doctor n'accède jamais directement à `.storage`.

Les registres sont obtenus via le WebSocket Home Assistant. Deux catégories sont séparées :

- **orphelin probable** : entrée active du registre sans aucun état correspondant ;
- **candidat local à revoir** : automation/script/helper/template simplement `unavailable`, ce qui ne suffit pas à prouver qu'il est obsolète.

Aucune suppression automatique n'est proposée ou effectuée.

## Rapport JSON 0.5

Les principaux blocs orientés utilisateur sont :

- `scores`
- `diagnostic_summary`
- `entity_health`
- `registry_analysis`
- `diagnostic_engine`
- `executive_summary`
- `action_plan`
- `diagnostic_explanations`
- `registry_observations`
- `findings`
- `diagnostics`

## Score Alpha

La 0.5 utilise `priority_v3-explain-preview`.

Les nouveaux diagnostics du registre et le moteur explicatif **ne modifient pas encore le score** :

- `registry_scoring: false`
- `explanatory_scoring: false`

Cette décision permet de comparer les rapports 0.4.x et 0.5.0 pendant la calibration sur plusieurs installations.

Le score reste un indice d'aide à la décision, pas une certification de sécurité ou de conformité.

## Analyse des blueprints

HA Doctor charge les blueprints présents dans `blueprints/automation`, applique les valeurs fournies via `use_blueprint.input` et résout les références `!input`. Les valeurs par défaut présentes dans un blueprint non utilisé ne sont pas considérées comme des références actives.

## Limitations Alpha 0.5

- Certaines références entièrement dynamiques en Jinja ne peuvent pas être résolues statiquement.
- Les conflits entre automatisations restent prudents lorsque l'exclusivité dépend de templates complexes.
- Les causes racines sont des diagnostics heuristiques avec niveau de confiance, pas des preuves absolues.
- HA Doctor ne consulte pas encore l'historique longue durée pour prouver qu'une indisponibilité persiste depuis plusieurs jours.
- Les logs ne sont pas encore corrélés automatiquement avec chaque incident.
- Zigbee2MQTT/MQTT sont encore analysés principalement via les entités et registres, sans diagnostic profond du maillage ou des topics.
- Toute modification de Home Assistant doit être validée humainement avant application.
