# HA Doctor 0.11.0 — Cross-Validated Engine

0.11 transforme les anomalies découvertes par un vrai rapport 0.10 en invariants de produit testés automatiquement.

## Corrections validées par le rapport réel

- La posture Sécurité est désormais dérivée directement des preuves du finding source. Un `HD-SEC-001` avec 3 preuves ne peut plus devenir `0` dans Product Intelligence.
- Maintenance applique la même règle à `HD-CFG-001` et `HD-REG-002`, en distinguant le total diagnostic de l’échantillon d’exemples.
- Diagnostic Trust reconnaît explicitement le snapshot HA unique à partir de `scan_performance` avant la construction de la vue produit.
- L'Executive Summary expose Controller Semantics V7 et Resilience Exposure First au lieu de libellés techniques devenus obsolètes.
- Les recommandations de résilience conservent les automatisations réellement concernées (`risky_automations`).
- Le rapport support conserve une preuve compacte pour chaque conflit physique restant : raison, intents opposés, overlap numérique littéral et absence d'exécution des templates.

## Cross-Section Truth V1

Une nouvelle section compare les compteurs client aux findings sources :

- secrets actifs / archives ;
- références absentes ;
- indisponibles locales à revoir ;
- preuve du snapshot unique ;
- nombre de conflits physiques expliqués ;
- traçabilité des recommandations de résilience.

## Self-Check V3

Le self-check réutilise les contrôles 0.10 puis ajoute :

- identité findings → Security Posture ;
- identité findings → Maintenance Intelligence ;
- preuve obligatoire sur toute paire physique non résolue ;
- automatisation concernée obligatoire pour toute recommandation de résilience exposée ;
- validation du texte Executive Summary V7 / Exposure First ;
- construction et validation du vrai Share Report pendant le scan ;
- contrôle du plafond 32 Ko et avertissement au-dessus de la cible 28 Ko ;
- identité du contenu Security/Maintenance entre rapport complet et export ;
- conservation de l'evidence Controller/Resilience dans l'export.

## Share Report V5

Le nouveau schéma `ha-doctor-share/5` reste borné 28/32 Ko, mais privilégie désormais la preuve essentielle avant les sections descriptives dupliquées.

## Invariants

- lecture seule ;
- aucune seconde lecture Home Assistant ;
- aucun état brut persisté ;
- aucun YAML brut persisté ;
- aucune valeur de secret exportée ;
- aucun template exécuté ;
- aucun auto-fix ;
- Score V4 primaire inchangé ; V5 reste une projection.
