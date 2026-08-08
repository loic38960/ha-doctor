# Security

HA Doctor 0.1.0 est conçu pour fonctionner en lecture seule.

Principes :
- aucun `full_access` ;
- aucun accès Docker ;
- aucun privilège matériel ;
- configuration Home Assistant montée en lecture seule ;
- `secrets.yaml` explicitement exclu du scanner ;
- `.storage` explicitement exclu du scanner V0.1 ;
- aucune valeur détectée comme sensible n'est incluse dans le rapport ;
- aucun état Home Assistant brut n'est persisté dans `report.json` ;
- aucune correction automatique.

Ne pas publier de rapport de diagnostic sans en vérifier le contenu : les noms d'entités et noms de fichiers peuvent révéler des informations sur l'installation.
