"""Surveillance du dossier source avec watchdog.

Seules les entrées situées directement dans le dossier surveillé nous
intéressent (surveillance non récursive) : ce qui se passe à l'intérieur d'un
sous-dossier est pris en compte par le calcul de stabilité de ce dossier.

Le gestionnaire ne fait aucun traitement lui-même : il transmet le chemin au
moteur, qui le confie au suivi de stabilité. Le thread de watchdog n'est
ainsi jamais bloqué.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)


class _Handler(FileSystemEventHandler):
    def __init__(self, root: Path, on_entry: Callable[[Path], None]) -> None:
        self.root = os.path.normcase(os.path.abspath(root))
        self.on_entry = on_entry

    def _forward(self, raw_path: str | bytes) -> None:
        path = os.fsdecode(raw_path)
        parent = os.path.normcase(os.path.dirname(os.path.abspath(path)))
        if parent == self.root:
            self.on_entry(Path(path))

    def on_created(self, event: FileSystemEvent) -> None:
        self._forward(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._forward(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Typiquement : « film.mp4.crdownload » renommé en « film.mp4 » à la
        # fin du téléchargement. Seule la destination compte.
        self._forward(event.dest_path)


class SourceWatcher:
    def __init__(self, root: Path, on_entry: Callable[[Path], None]) -> None:
        self.root = root
        self._observer = Observer()
        self._observer.daemon = True
        self._observer.schedule(_Handler(root, on_entry), str(root), recursive=False)

    def start(self) -> None:
        self._observer.start()
        log.info("Surveillance démarrée sur %s", self.root)

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)
        log.info("Surveillance arrêtée")

    @property
    def alive(self) -> bool:
        return self._observer.is_alive()

# GROGNON
