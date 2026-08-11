# HA Doctor 0.16.1 — Publication Hotfix

Hotfix issu du premier rapport réel 0.16.0.

## Corrigé

- normalisation de tous les playbooks hérités vers `repair_playbook_v4_precision_evidence` avant Self-Check ;
- distinction explicite entre exposition pré-contrôle **non protégée** (`must_fix`) et fallback pré-contrôle **weak** (`hardening`) ;
- suppression du faux échec `resilience.pre_not_downgraded` sur les fallbacks faibles ;
- Share V10 compacté en supprimant les représentations dupliquées de la même vérité ;
- cible Share maintenue à 20 Ko, plafond dur maintenu à 24 Ko ;
- version App portée à 0.16.1 pour distribuer correctement le correctif.

## Inchangé

- score technique ;
- findings et action plan ;
- Controller Impact V2 ;
- Condition Semantics V11 ;
- Decision Engine V4 ;
- Temporal V7 ;
- contrat d'historique canonique ;
- lecture seule stricte et absence d'auto-fix.

Le correctif n'ajoute aucune lecture Home Assistant et ne modifie aucune configuration utilisateur.
