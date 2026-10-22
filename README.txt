ORDO
====

Petit logiciel qui range automatiquement le dossier Téléchargements.

Mon dossier Téléchargements finissait toujours par contenir 300 fichiers
nommés "document (3).pdf" ou "IMG_20261021_1830.jpg". Ordo surveille le
dossier, et dès qu'un téléchargement est terminé il propose de le renommer
proprement et de le ranger au bon endroit. Les PDF vont dans Documents,
les photos dans Images, etc.

Par défaut, il ne déplace rien sans demander : chaque fichier attend dans
l'onglet "À valider". On peut changer le nom ou la destination, refuser
un fichier, puis tout valider d'un coup. Et si on s'est trompé, l'onglet
"Historique" permet d'annuler.


CE QU'IL FAIT
-------------

- Il attend que le téléchargement soit vraiment fini avant de toucher
  au fichier (il ignore les .crdownload, .part, etc.).

- Il renomme les fichiers :
      Rapport d'Été FINAL (1).PDF  ->  2026-10-22_rapport_d_ete_final.pdf
  Les accents, les espaces et les "(1)" ou "- Copie" disparaissent, et
  la date est ajoutée devant.

- Il range par catégorie : Documents, Images, Vidéos, Audio, Archives,
  Code, Installeurs, Polices. Les fichiers qu'il ne connaît pas restent
  où ils sont.

- On peut ajouter des règles sur le nom. Par exemple, tout ce qui
  contient "facture" part dans Documents/Factures.

- Il repère les doublons : si exactement le même fichier est déjà rangé,
  le nouveau part dans un dossier _Doublons au lieu d'être rangé une
  deuxième fois. Il ne supprime jamais rien.

- Les .zip sont rangés et décompressés automatiquement.

- Il peut tourner en arrière-plan (icône à côté de l'horloge), envoyer
  des notifications et se lancer au démarrage de l'ordinateur.

Tout se règle dans l'onglet "Réglages".


INSTALLATION
------------

Il faut Python 3.11 ou plus récent (https://www.python.org).
Sous Windows, cocher "Add Python to PATH" pendant l'installation.

Dans un terminal, depuis le dossier qui contient main.py :

    python -m venv .venv
    .venv\Scripts\activate          (sous Mac/Linux : source .venv/bin/activate)
    pip install -r requirements.txt
    python main.py

Les fois suivantes, il suffit de faire les deux commandes "activate" et
"python main.py".


EN FAIRE UN .EXE
----------------

    pip install -r requirements-dev.txt
    pyinstaller ordo.spec --noconfirm

L'exécutable se retrouve dans le dossier dist/. Il faut le construire
sur le système visé : le .exe sous Windows, le .app sur un Mac.

Au premier lancement, Windows peut afficher "Windows a protégé votre
ordinateur", parce que l'exécutable n'est pas signé. Cliquer sur
"Informations complémentaires" puis "Exécuter quand même".


COMMENT C'EST ORGANISÉ
----------------------

main.py         lance l'application
app/config      les réglages et leurs valeurs par défaut
app/core        toute la logique : surveillance, tri, renommage,
                doublons, historique (aucun code d'interface ici)
app/fs          les déplacements de fichiers et les archives
app/system      notifications, lancement au démarrage
app/gui         l'interface (CustomTkinter)
tests           les tests, à lancer avec : python -m pytest

Les réglages et l'historique sont enregistrés dans le dossier utilisateur
(AppData sous Windows). Réglages > Avancé permet de les ouvrir directement.
