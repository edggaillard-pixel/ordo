"""Ordo — rangement automatique des fichiers entrants.

Le paquet est découpé en couches indépendantes :

- ``app.config`` : réglages (lecture, validation, sauvegarde JSON) ;
- ``app.core``   : logique métier pure (classement, renommage, doublons,
  planification, exécution, journal, surveillance). N'importe jamais la GUI ;
- ``app.fs``     : opérations sur le système de fichiers (déplacement sûr,
  extraction d'archives) ;
- ``app.system`` : intégration au système (notifications, démarrage auto,
  chemins standards, instance unique) ;
- ``app.gui``    : interface CustomTkinter, qui ne fait que piloter le moteur.
"""

APP_NAME = "Ordo"
APP_AUTHOR = "Ordo"
APP_ID = "com.ordo.app"
__version__ = "1.0.0"
