# Security

HA Doctor 0.2.0 Alpha est conçu pour fonctionner en lecture seule.

Principes :
- aucun `full_access` ;
- aucun accès Docker ;
- aucun privilège matériel ;
- interface exposée uniquement via Home Assistant Ingress ;
- configuration Home Assistant montée en lecture seule ;
- `secrets.yaml` / `secrets.yml` explicitement exclus du scanner ;
- `.storage` intégralement exclu du scanner ;
- bases, clés, certificats, sauvegardes et archives exclus ;
- aucune valeur détectée comme sensible n'est incluse dans le rapport ;
- aucun état Home Assistant brut n'est persisté dans `report.json` ;
- aucune correction automatique.

Les noms d'entités, d'automatisations et de fichiers peuvent eux-mêmes révéler des informations sur une installation. Un rapport HA Doctor ne doit donc pas être publié sans vérification préalable.
