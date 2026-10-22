"""Opérations sur le système de fichiers, sans jamais écraser de données.

``safe_move`` garantit qu'un déplacement ne remplace jamais un fichier
existant, y compris quand un autre programme crée ce fichier au même instant :

- même disque, Windows : ``os.rename`` refuse nativement d'écraser ;
- même disque, macOS / Linux : lien physique puis suppression de l'original
  (``os.link`` échoue si la destination existe, de façon atomique) ;
- disques différents : copie vers un nom temporaire caché dans le dossier
  cible, renommage final, puis suppression de l'original.

Les erreurs passagères (fichier verrouillé par un antivirus, un indexeur…)
sont retentées quelques fois avant d'abandonner.
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

RETRIES = 4
RETRY_DELAY = 0.5  # secondes, doublé à chaque essai


class DestinationExists(FileExistsError):
    """La destination est apparue entre la vérification et le déplacement."""


def safe_move(source: Path, destination: Path) -> Path:
    """Déplace ``source`` vers ``destination`` (fichier ou dossier)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    delay = RETRY_DELAY
    for attempt in range(1, RETRIES + 1):
        try:
            _move_once(source, destination)
            return destination
        except DestinationExists:
            raise
        except PermissionError as exc:
            if attempt == RETRIES:
                raise
            log.debug("Fichier verrouillé (%s), nouvel essai dans %.1fs", exc, delay)
            time.sleep(delay)
            delay *= 2
    return destination  # pour les analyseurs statiques


def _move_once(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise DestinationExists(str(destination))

    if sys.platform == "win32":
        try:
            os.rename(source, destination)  # n'écrase jamais sous Windows
            return
        except FileExistsError as exc:
            raise DestinationExists(str(destination)) from exc
        except OSError as exc:
            if getattr(exc, "winerror", None) != 17:  # 17 = autre disque
                raise
        _cross_device_move(source, destination)
        return

    if source.is_dir():
        # Les dossiers ne peuvent pas avoir de lien physique : la fenêtre de
        # concurrence se limite à la vérification ci-dessus.
        try:
            os.rename(source, destination)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            _cross_device_move(source, destination)
        return

    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise DestinationExists(str(destination)) from exc
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            _cross_device_move(source, destination)
            return
        # Système de fichiers sans liens physiques (FAT, exFAT, certains
        # partages réseau) : renommage classique après vérification.
        if exc.errno in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EMLINK, errno.EACCES):
            if destination.exists():
                raise DestinationExists(str(destination)) from exc
            os.rename(source, destination)
            return
        raise
    os.unlink(source)


def _cross_device_move(source: Path, destination: Path) -> None:
    """Copie complète vers un nom temporaire, renommage, puis suppression."""
    tmp = destination.with_name(f".ordo-{uuid.uuid4().hex[:8]}.tmp")
    try:
        if source.is_dir():
            shutil.copytree(source, tmp, symlinks=True)
        else:
            shutil.copy2(source, tmp)
        if destination.exists():
            raise DestinationExists(str(destination))
        os.rename(tmp, destination)
    except BaseException:
        if tmp.is_dir():
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    if source.is_dir():
        shutil.rmtree(source)
    else:
        source.unlink()


def send_to_trash(path: Path) -> None:
    """Envoie à la corbeille du système (jamais de suppression définitive)."""
    from send2trash import send2trash

    send2trash(str(path))


def open_in_file_manager(path: Path) -> None:
    """Ouvre un dossier (ou le dossier d'un fichier) dans l'explorateur."""
    import subprocess

    target = path if path.is_dir() else path.parent
    if sys.platform == "win32":
        if path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if path.is_file() else ["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])

# GROGNON
