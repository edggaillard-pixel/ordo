"""Détection de la fin d'un téléchargement.

Un fichier n'est traité que lorsque TOUTES ces conditions sont réunies :

1. il ne porte pas une extension temporaire (``.crdownload``, ``.part``…) ;
2. aucun « frère » temporaire n'existe à côté. Firefox crée par exemple
   ``video.mp4`` vide ET ``video.mp4.part`` pendant le téléchargement ;
3. sa taille et sa date de modification n'ont pas bougé depuis N secondes ;
4. il n'est plus verrouillé par un autre programme (test fiable sous Windows,
   où un fichier ouvert en écriture ne peut pas être renommé).

Pour un dossier, la « taille » est la somme de son contenu.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

Signature = tuple[int, int, int]  # (taille, nombre d'éléments, mtime max)

# Au-delà, on considère qu'un dossier est stable sans tout parcourir.
_MAX_DIR_ENTRIES = 20_000


def has_temp_extension(name: str, temp_extensions: Iterable[str]) -> bool:
    lower = name.lower()
    return any(lower.endswith("." + ext.lower().lstrip(".")) for ext in temp_extensions)


def has_temp_sibling(path: Path, temp_extensions: Iterable[str]) -> bool:
    """Vrai si ``nom.ext.part`` (ou équivalent) existe à côté de ``nom.ext``."""
    for ext in temp_extensions:
        if path.with_name(path.name + "." + ext.lstrip(".")).exists():
            return True
    return False


def signature(path: Path) -> Signature | None:
    try:
        st = path.stat()
    except OSError:
        return None
    if not path.is_dir():
        return (st.st_size, 1, st.st_mtime_ns)

    total, count, newest = 0, 0, st.st_mtime_ns
    for root, dirs, files in os.walk(path):
        for name in files:
            try:
                fst = os.stat(os.path.join(root, name))
            except OSError:
                continue
            total += fst.st_size
            newest = max(newest, fst.st_mtime_ns)
            count += 1
        count += len(dirs)
        if count > _MAX_DIR_ENTRIES:
            break
    return (total, count, newest)


def is_unlocked(path: Path) -> bool:
    """Le fichier peut-il être déplacé maintenant ?

    Sous Windows, renommer un fichier vers lui-même échoue tant qu'un autre
    programme le garde ouvert : c'est un test de verrou sans effet de bord.
    Ailleurs, un fichier ouvert peut être déplacé, on se fie à la stabilité.
    """
    if sys.platform != "win32":
        return path.exists()
    try:
        os.rename(path, path)
        return True
    except OSError:
        return False


@dataclass
class _Tracked:
    signature: Signature | None
    changed_at: float
    first_seen: float


class StabilityTracker:
    """Suit les entrées en cours d'arrivée et signale celles qui sont prêtes.

    Thread-safe : ``touch`` est appelé par le thread de surveillance, ``poll``
    par le thread de traitement.
    """

    def __init__(
        self,
        stable_seconds: float,
        temp_extensions: Iterable[str],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.stable_seconds = stable_seconds
        self.temp_extensions = list(temp_extensions)
        self._clock = clock
        self._items: dict[Path, _Tracked] = {}
        self._lock = threading.Lock()

    def touch(self, path: Path) -> None:
        """Signale qu'une entrée vient d'apparaître ou de changer."""
        now = self._clock()
        with self._lock:
            tracked = self._items.get(path)
            if tracked is None:
                self._items[path] = _Tracked(None, now, now)
            else:
                tracked.changed_at = now

    def discard(self, path: Path) -> None:
        with self._lock:
            self._items.pop(path, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def poll(self) -> list[Path]:
        """Renvoie (et oublie) les entrées stables, prêtes à être traitées."""
        now = self._clock()
        with self._lock:
            snapshot = list(self._items.items())

        ready: list[Path] = []
        for path, tracked in snapshot:
            if not path.exists() and not path.is_symlink():
                self.discard(path)  # supprimé ou renommé entre-temps
                continue
            sig = signature(path)
            if sig != tracked.signature:
                tracked.signature = sig
                tracked.changed_at = now
                continue
            if now - tracked.changed_at < self.stable_seconds:
                continue
            if has_temp_sibling(path, self.temp_extensions):
                tracked.changed_at = now  # téléchargement Firefox en cours
                continue
            if not path.is_dir() and not is_unlocked(path):
                tracked.changed_at = now
                continue
            ready.append(path)

        with self._lock:
            for path in ready:
                self._items.pop(path, None)
        return ready
