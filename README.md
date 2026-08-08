# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est un prototype de diagnostic **local, explicatif et en lecture seule** pour Home Assistant OS. Il analyse l'installation, corrèle les symptômes et produit un plan d'action sans appliquer de modification automatique.

## Alpha 0.7 — diagnostic corrélé et architecture

La 0.7 est une évolution majeure du moteur : HA Doctor ne se contente plus de compter des entités ou d'énumérer des règles. Il tente de répondre à quatre questions :

1. **Quel est le vrai problème ?**
2. **Quelle cause commune explique le plus de symptômes ?**
3. **Quelles automatisations sont réellement exposées ?**
4. **La situation s'améliore-t-elle ou se dégrade-t-elle dans le temps ?**

### Score V4

Le score `root_cause_temporal_v4` est calculé après corrélation des diagnostics.

Il tient compte de :

- la priorité ;
- la sévérité ;
- la confiance ;
- la persistance sur plusieurs scans ;
- l'impact réel dans le graphe d'automatisations ;
- la différence entre actionneur, capteur, helper et fonction optionnelle ;
- des plafonds par catégorie afin d'éviter qu'une seule panne ne soit comptée plusieurs fois.

Les volumes bruts `unavailable` et `unknown` restent visibles mais **ne pénalisent pas directement le score** lorsqu'une cause racine les explique.

### Graphe de dépendances V2

Le graphe distingue désormais :

- entités de déclenchement ;
- entités commandées ;
- entités simplement lues ;
- appels de services Home Assistant.

Les appels comme `switch.turn_on`, `input_number.set_value`, `climate.set_temperature` ou `todo.get_items` sont filtrés : ils ne sont plus traités comme des `entity_id`.

Le rapport expose :

- nombre de nœuds d'automatisations ;
- nombre d'arêtes d'entités ;
- triggers ;
- contrôles ;
- appels de services retirés.

### Blast radius réel

Une dépendance sur un actionneur physique n'a plus le même poids qu'un helper partagé.

HA Doctor distingue notamment :

- **actionneur** : switch, climate, cover, light, lock, siren, vacuum… ;
- **capteur / état métier** ;
- **helper** : input_boolean, input_number, input_datetime, counter… ;
- **fonction optionnelle**.

Le fan-out des helpers est fortement décoté afin qu'un helper de coordination utilisé partout ne fasse pas artificiellement apparaître une panne critique.

Chaque diagnostic peut exposer :

- automatisations impactées ;
- automatisations réellement critiques ;
- dépendances uniquement liées à des helpers ;
- niveau d'impact `low / medium / high` ;
- score d'impact pondéré.

### Analyse d'architecture

Le nouveau bloc `architecture_analysis` produit une cartographie synthétique de l'installation :

- score de complexité ;
- hotspots d'entités ;
- actionneurs commandés par plusieurs automatisations ;
- helper hubs ;
- trigger hubs ;
- boucles trigger → commande ;
- automatisations les plus interconnectées ;
- fichiers concentrant le plus de logique.

Le score de complexité est informatif : une installation complexe n'est pas automatiquement considérée comme en mauvaise santé.

### Régressions et historique V2

HA Doctor conserve les 20 derniers scans dans `/data/ha-doctor-history.json`.

Seuls sont conservés :

- dates ;
- scores ;
- compteurs ;
- identifiants de diagnostics ;
- quelques métriques agrégées d'architecture.

Aucune valeur brute d'état n'est persistée.

La 0.7 sait distinguer :

- diagnostic nouveau ;
- persistant ;
- récurrent ;
- résolu ;
- score stable, amélioré ou dégradé.

L'historique 0.6/V3 reste lisible lors de la migration vers V4.

### Dette de maintenance

Le bloc `maintenance_debt` donne un indicateur séparé de la santé :

- références YAML absentes ;
- orphelins probables ;
- anciennes entités locales à revoir ;
- archives contenant potentiellement des secrets ;
- écart entre automatisations YAML analysées et entités automation actives.

Une forte dette de maintenance ne signifie pas nécessairement une panne immédiate.

### Quality gates

HA Doctor vérifie désormais aussi la qualité de son propre rapport :

- API Home Assistant accessible ;
- YAML parsable ;
- blueprints résolus ;
- registres accessibles ;
- garanties de confidentialité respectées ;
- graphe nettoyé ;
- compteurs du résumé synchronisés avec le plan final.

### Interface 0.7

L'interface Ingress est organisée en six vues :

1. **Vue d'ensemble** — score V4, verdict, évolution, priorités et quality gates ;
2. **Plan d'action** — recherche et filtres priorité/domaine/confiance ;
3. **Architecture** — hotspots, actionneurs partagés et automatisations complexes ;
4. **Intégrations & appareils** — causes racines et périphériques touchés ;
5. **Historique** — évolution du score et cycle de vie des diagnostics ;
6. **Qualité & confidentialité** — quality gates, dette technique et garanties de privacy.

### API locale

Principaux endpoints Ingress :

- `/api/status`
- `/api/version`
- `/api/report`
- `/api/summary`
- `/api/insights`
- `/api/actions`
- `/api/architecture`
- `/api/quality`
- `/api/history`
- `/api/diagnostic?id=DX-...`
- `/api/download`
- `/api/download-summary`
- `/api/download-anonymized`
- `/health`

## Confidentialité et sécurité

HA Doctor n'effectue que des lectures dans son fonctionnement actuel.

- `/ha_config` est monté en lecture seule ;
- `secrets.yaml` n'est pas lu ;
- `.storage` n'est pas parcouru directement ;
- bases de données, clés privées, certificats et sauvegardes binaires sont exclus ;
- les valeurs brutes des états ne sont pas persistées ;
- le token Supervisor et les payloads bruts du registre ne sont pas enregistrés ;
- aucune correction, suppression, désactivation ou redémarrage n'est exécuté automatiquement ;
- le moteur explicatif fonctionne localement sans IA externe.

L'export anonymisé retire les `entity_id`, noms d'appareils, intégrations, automatisations et chemins de fichiers tout en conservant les métriques agrégées utiles au diagnostic.

## Installation via dépôt personnalisé

Dans Home Assistant :

1. Ouvrir **Paramètres → Apps → App Store**.
2. Ouvrir **⋮ → Dépôts**.
3. Ajouter `https://github.com/loic38960/ha-doctor`.
4. Rechercher les mises à jour de l'App Store.
5. Installer ou mettre à jour **HA Doctor**.
6. Démarrer l'App et ouvrir son interface Web.

## Robustesse du packaging

Depuis la 0.7, le Dockerfile copie automatiquement tous les modules Python du répertoire App au lieu d'utiliser une liste de fichiers maintenue manuellement.

La CI exécute à chaque push :

- tous les tests unitaires ;
- compilation de tous les modules Python ;
- validation des marqueurs UI et des versions ;
- **construction réelle de l'image Home Assistant App** ;
- vérification de la présence des modules packagés ;
- import de `app`, `scanner_v070`, `intelligence_v070` et `share_export` dans le conteneur construit ;
- vérification des assets Web dans l'image.

Cette chaîne est conçue pour détecter avant installation les erreurs de packaging du type `ModuleNotFoundError`.

## Limites Alpha

- les références Jinja entièrement dynamiques ne sont pas toujours résolubles statiquement ;
- les conflits complexes entre automatisations peuvent nécessiter une validation humaine ;
- les causes racines restent des diagnostics probabilistes avec niveau de confiance ;
- le maillage Zigbee et les logs détaillés ne sont pas encore analysés aussi profondément que le YAML et les registres ;
- aucune correction automatique n'est effectuée.

Le score HA Doctor est un indicateur de diagnostic et de maintenance, pas une certification de sécurité ou de conformité.
