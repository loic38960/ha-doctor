# HA Doctor 0.9.0 — Milestone Release

La 0.9.0 marque le passage d'un moteur surtout technique à un produit de diagnostic utilisable directement par un propriétaire Home Assistant.

## Résultat attendu

Un scan doit désormais fournir deux niveaux de lecture :

1. le rapport technique complet pour l'analyse avancée ;
2. une vue courte qui dit quoi traiter, dans quel ordre, avec quelle confiance.

## Lot livré

### Triage et décision

1. Doctor View V1.
2. Verdict client séparé du score technique.
3. Lane `fix_now`.
4. Lane `investigate`.
5. Lane `review`.
6. Lane `optimize`.
7. Lane `watch`.
8. Risk score normalisé 0–100.
9. Confiance A/B/C/D par action.
10. Type de réparation générique.
11. Estimation d'effort.
12. Intégration du blast radius au tri.
13. Intégration de la persistance au tri.
14. Intégration de la confiance au tri.
15. Intégration des scénarios de gain Score V5.
16. Liste des sept prochaines meilleures actions.
17. Projection après les trois premières corrections.
18. Compression explicite des observations gardées hors plan.
19. Change Digest V1.
20. Présentation séparée des nouveaux/persistants/résolus/déclassés.

### Confiance et auto-diagnostic

21. Diagnostic Trust V1.
22. Score de confiance du scan indépendant du score HA.
23. Prise en compte des quality gates.
24. Prise en compte de la cohérence interne.
25. Prise en compte de Flow Confidence.
26. Prise en compte des erreurs de lineage.
27. Prise en compte des cibles dynamiques non résolues.
28. Report Self-Check V1.
29. Contrôle version/schéma.
30. Contrôle bornes des scores.
31. Contrôle compteurs de sévérité.
32. Contrôle unicité des rule IDs.
33. Contrôle unicité des action IDs.
34. Contrôle identité `action_plan.total`.
35. Contrôle identité des compteurs de priorité.
36. Contrôle `diagnostic_summary.plan_id_count`.
37. Contrôle des paires Controller Semantics.
38. Contrôle des entités du Controller Review Summary.
39. Contrôle des compteurs Resilience V4.
40. Contrôle des taux Flow.
41. Contrôle des compteurs temporels.
42. Contrôle des compteurs d'inventaire.
43. Contrôle des invariants de lecture seule.
44. Contrôle de l'absence de nouvelles lectures d'état 0.9.
45. Contrôle sérialisation JSON.
46. Contrôle caractère NUL.
47. Contrôle de taille locale anormale.
48. Quality Gate dédié au Self-Check.
49. Release Readiness V1.
50. Blocage logique de publication si Self-Check échoue.
51. Dégradation automatique de Diagnostic Trust en cas d'échec interne.

### Exports et interface

52. Share Report V3.
53. Nouveau schéma `ha-doctor-share/3`.
54. Cible d'export abaissée à 28 Ko.
55. Plafond dur abaissé à 32 Ko.
56. Conservation de toutes les identités d'actions.
57. Conservation de toutes les identités de findings.
58. Stratégie d'allègement progressive.
59. Fallback `identity_first`.
60. Doctor View inclus dans l'export support.
61. Self-Check inclus dans l'export support.
62. Nouveau résumé Markdown lisible.
63. Endpoint `/api/doctor-view`.
64. Endpoint `/api/self-check`.
65. Endpoint `/api/download-support-summary`.
66. `/api/version` explicite pour 0.9.
67. Carte de verdict 0.9 dans l'overview.
68. Carte prochaine action.
69. Carte confiance du diagnostic.
70. Compteurs de triage.
71. Indicateur de compression du bruit.
72. Bloc ordre recommandé dans Plan d'action.
73. Bloc Self-Check dans Qualité.
74. Bouton `Résumé lisible`.
75. Bouton `Rapport support · compact`.

### Robustesse et continuité

76. Scanner 0.9 sans seconde lecture HA.
77. Conservation du pipeline 0.8.8 éprouvé.
78. Conservation Controller Semantics V6.
79. Conservation Resilience V4.
80. Conservation Entity Lineage V1.
81. Conservation Registry Blast Radius V4.
82. Conservation Temporal V3.1.
83. Score V4 toujours primaire.
84. Score V5 toujours preview non destructif.
85. Aucun auto-fix.
86. Aucun nouveau write endpoint.
87. Tests unitaires Product V1.
88. Tests Self-Check.
89. Tests Release Readiness.
90. Tests Share V3 borné.
91. Tests de conservation des IDs.
92. Tests du résumé Markdown.
93. Tests UI 0.9.
94. Validation JavaScript via Node.
95. Build Docker réel en CI.
96. Smoke test des endpoints 0.9.
97. Smoke test du téléchargement JSON.
98. Smoke test du téléchargement Markdown.
99. Non-régression V6/V4 dans l'image packagée.
100. Passage à une politique de **milestones** au lieu des micro-releases.

## Invariants

- Home Assistant reste en lecture seule côté HA Doctor.
- `secrets.yaml` n'est pas lu.
- Aucun état brut n'est persisté dans l'historique.
- Aucun YAML brut ou texte de template n'est ajouté à l'historique 0.9.
- Aucun service IA externe n'est appelé.
- Le Score V4 historique n'est pas réécrit par la couche produit.

## Migration

La 0.9.0 s'appuie sur le rapport 0.8.8 et reste compatible avec ses sections techniques. Les nouvelles sections sont additives : `doctor_view`, `triage_board`, `diagnostic_trust`, `self_check`, `release_readiness` et `change_digest`.
