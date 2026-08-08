# HA Doctor

**Le contrôle technique de votre Home Assistant.**

HA Doctor est un prototype de diagnostic **local, explicatif et en lecture seule** pour Home Assistant OS. Il analyse l'installation, corrèle les symptômes, étudie les dépendances entre automatisations et produit un plan d'action sans appliquer de modification automatique.

## Alpha 0.8 — Entity Flow V3

La 0.8 approfondit surtout une faiblesse des versions précédentes : comprendre ce qu'une automatisation **fait réellement**, même lorsqu'elle utilise des blueprints, des variables ou des cibles Jinja.

Le moteur cherche désormais à répondre à six questions :

1. **Quel est le vrai problème ?**
2. **Quelle cause commune explique les symptômes ?**
3. **Quelles automatisations sont réellement exposées ?**
4. **Quels équipements sont effectivement commandés ?**
5. **Quelles cibles dynamiques HA Doctor sait-il prouver ou seulement supposer ?**
6. **La situation s'améliore-t-elle ou se dégrade-t-elle dans le temps ?**

### Entity Flow V3

Le graphe `entity_flow_v3` distingue maintenant :

- `triggers` — entités qui déclenchent une automatisation ;
- `controls` — entités réellement commandées ;
- `calls` — scripts, scènes ou automatisations invoqués ;
- `reads` — entités simplement consultées ;
- `dynamic_controls` — cibles dynamiques résolues avec un niveau de confiance ;
- `unresolved_dynamic_targets` — cibles que l'analyse statique ne peut pas démontrer.

HA Doctor tente notamment de résoudre :

```yaml
variables:
  pompe_entity: switch.pompe_piscine

action:
  - action: switch.turn_on
    target:
      entity_id: "{{ pompe_entity }}"
```

ainsi que les chaînes de variables et les ensembles de cibles possibles, par exemple une variable pouvant désigner plusieurs `climate.*`.

HA Doctor **n'exécute jamais les templates Jinja** pour cette analyse. Il utilise uniquement une résolution statique prudente.

### Confiance des cibles dynamiques

Une cible peut être classée selon la preuve disponible :

- cible statique explicite ;
- lignée de variable déterministe ;
- plusieurs cibles possibles ;
- inférence prudente par domaine ;
- non résolue.

Une cible non démontrable n'est pas inventée. Le quality gate de flux indique le taux de résolution réel du scan.

### Appels de scripts séparés des commandes

Un appel à :

```yaml
script.notifier_mogo_loic
```

n'est plus traité comme une lecture ou un actionneur physique.

Le graphe possède un type d'arête `calls`, ce qui permet d'identifier :

- scripts de notification partagés ;
- scènes communes ;
- automatisations invoquées par d'autres automatisations ;
- hubs d'appel.

### Architecture V2

Le bloc `architecture_analysis` utilise maintenant le graphe V3 et expose :

- score de complexité ;
- hotspots d'entités ;
- actionneurs partagés ;
- helper hubs ;
- trigger hubs ;
- call hubs ;
- dépendances critiques ;
- boucles trigger → commande ;
- automatisations à risque architectural élevé ;
- cibles dynamiques non résolues.

Le score de complexité reste informatif : une installation complexe n'est pas automatiquement considérée en mauvaise santé.

### Risk Index V2

Le calcul du risque architectural des automatisations a été recalibré.

Les commandes vers des équipements physiques ont maintenant beaucoup plus de poids que les simples lectures. Les domaines de sécurité comme `alarm_control_panel`, `lock` et `siren` reçoivent une pondération renforcée.

À l'inverse, le nombre de lectures est **logarithmique et plafonné** : une automatisation qui inspecte 50 capteurs ne devient plus artificiellement plus dangereuse qu'une automatisation qui pilote plusieurs actionneurs.

### Blast Radius V2

Chaque diagnostic peut maintenant exploiter :

- dépendances de trigger ;
- dépendances de commande ;
- appels de scripts/scènes ;
- lectures ;
- commandes dynamiques possibles ;
- niveau de confiance de la résolution ;
- automatisations impactées ;
- automatisations à risque élevé.

Les helpers partagés restent fortement décotés afin d'éviter un faux blast radius massif.

### Couverture des automatisations V2

La 0.8 ne divise plus naïvement :

`automatisations YAML / toutes les entités automation du registre`.

La couverture compare maintenant les automatisations analysées aux automatisations **runtime actuellement disponibles**.

Les anciennes entrées `automation.*` en état `unavailable` sont suivies séparément comme dette de maintenance potentielle et ne créent plus automatiquement un faux trou de couverture.

Le rapport expose notamment :

- automatisations YAML analysées ;
- automatisations runtime totales ;
- automatisations runtime disponibles ;
- automatisations `unavailable` ;
- couverture réelle ;
- écart de couverture ;
- candidats d'anciennes entrées registry.

### Dette de maintenance V2

`maintenance_debt_v2` est séparée de l'indice de santé.

Elle distingue :

- références YAML absentes ;
- orphelins réellement probables ;
- simples candidats registry à revoir ;
- archives contenant potentiellement des secrets ;
- vrai écart de couverture ;
- doublons d'automatisations ;
- actions identiques consécutives ;
- attentes longues.

Les signaux faibles ne sont plus pénalisés comme des erreurs confirmées et une protection limite le double comptage d'un même problème.

### Score V4 conservé

La 0.8 conserve volontairement l'échelle `Score V4` introduite en 0.7 afin que l'historique reste comparable pendant la migration du graphe.

Le score tient toujours compte de :

- priorité ;
- sévérité ;
- confiance ;
- persistance ;
- causes racines ;
- impact des dépendances ;
- plafonds de pénalité par domaine.

Les volumes bruts `unavailable` et `unknown` restent informatifs et ne pénalisent pas directement le score lorsqu'une cause racine les explique.

### Historique et régressions

HA Doctor conserve jusqu'à 20 snapshots agrégés dans `/data/ha-doctor-history.json`.

Sont conservés uniquement :

- dates ;
- scores ;
- compteurs ;
- identifiants de diagnostics ;
- quelques métriques agrégées d'architecture ;
- taux agrégés de résolution des flux ;
- taux de couverture.

Aucun état brut, YAML brut ou texte de template dynamique n'est persisté.

### Quality Gates V2

HA Doctor contrôle aussi la qualité de son propre diagnostic :

- API Home Assistant ;
- parsing YAML ;
- résolution des blueprints ;
- registres Home Assistant ;
- confidentialité ;
- cohérence du rapport ;
- **résolution des flux d'entités** ;
- **couverture réelle des automatisations** ;
- **historique temporel**.

Le gate de flux tient compte du taux de cibles comprises, du taux de résolution des cibles dynamiques et des éventuelles erreurs de relecture sémantique.

## Interface

L'interface Ingress conserve les six vues principales :

1. **Vue d'ensemble** — Score V4, verdict, évolution et priorités ;
2. **Plan d'action** — diagnostics corrélés et filtres ;
3. **Architecture** — hotspots, actionneurs partagés et automatisations complexes ;
4. **Intégrations & appareils** — causes racines et périphériques touchés ;
5. **Historique** — évolution et persistance ;
6. **Qualité & confidentialité** — quality gates et dette de maintenance.

Les API 0.8 exposent en plus les nouvelles métriques de flux et de couverture.

## API locale

Principaux endpoints Ingress :

- `/api/status`
- `/api/version`
- `/api/report`
- `/api/summary`
- `/api/insights`
- `/api/actions`
- `/api/architecture`
- `/api/quality`
- `/api/flow`
- `/api/coverage`
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
- les registres sont interrogés via l'API WebSocket Home Assistant ;
- bases de données, clés privées, certificats et sauvegardes binaires sont exclus ;
- les valeurs brutes des états ne sont pas persistées ;
- le token Supervisor et les payloads bruts du registre ne sont pas enregistrés ;
- le YAML reparsé par Entity Flow V3 n'est pas persisté ;
- le texte brut des cibles Jinja n'est pas enregistré dans le rapport ;
- les payloads d'appels de scripts ne sont pas persistés ;
- aucune correction, suppression, désactivation ou redémarrage n'est exécuté automatiquement ;
- le moteur fonctionne localement sans IA externe.

L'export anonymisé retire les identifiants locaux et conserve uniquement les métriques nécessaires au partage d'un diagnostic.

## Installation via dépôt personnalisé

Dans Home Assistant :

1. Ouvrir **Paramètres → Apps → App Store**.
2. Ouvrir **⋮ → Dépôts**.
3. Ajouter `https://github.com/loic38960/ha-doctor` si nécessaire.
4. Rechercher les mises à jour de l'App Store.
5. Installer ou mettre à jour **HA Doctor**.
6. Démarrer l'App et ouvrir son interface Web.

## Robustesse du packaging

Le Dockerfile copie automatiquement tous les modules Python du répertoire App avec `COPY *.py ./`.

La CI exécute à chaque push :

- tous les tests unitaires ;
- compilation de tous les modules Python ;
- validation des marqueurs UI ;
- validation de la cohérence des versions 0.8 ;
- construction réelle de l'image Home Assistant App ;
- vérification de la présence des modules packagés ;
- import de `app_v080`, `scanner_v080`, `intelligence_v080`, `flow_v080` et des dépendances dans le conteneur construit ;
- vérification des assets Web.

Cette chaîne vise à détecter avant installation aussi bien les régressions logiques que les erreurs de packaging du type `ModuleNotFoundError`.

## Limites Alpha

- certains templates Jinja réellement calculés à l'exécution resteront non résolubles statiquement ;
- une cible dynamique avec plusieurs possibilités est volontairement présentée comme possible, pas certaine ;
- les conflits complexes entre automatisations nécessitent parfois une validation humaine ;
- les causes racines restent des diagnostics probabilistes avec niveau de confiance ;
- le maillage Zigbee, les statistiques Recorder et les logs détaillés peuvent encore être approfondis ;
- aucune correction automatique n'est effectuée.

Le score HA Doctor est un indicateur de diagnostic et de maintenance, pas une certification de sécurité ou de conformité.
