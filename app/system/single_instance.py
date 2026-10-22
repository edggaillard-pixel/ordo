"""Empêche deux instances de surveiller le même dossier en même temps.

Deux instances se disputeraient les mêmes fichiers. On pose un verrou
système sur un fichier : il est libéré automatiquement par le système si
l'application plante, contrairement à un simple fichier « .pid ».
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class SingleInstance:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "ordo.lock"
        self._fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")  # noqa: SIM115 - gardé ouvert exprès
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            self._fh = None
            return False
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        return True

    def release(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

# GROGNON
