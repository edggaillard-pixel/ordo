"""Fichiers que l'utilisateur a refusés (« Ignorer ») ou restaurés (« Annuler »).

Ils ne sont plus proposés tant qu'ils ne changent pas : l'empreinte
(taille + date de modification) est mémorisée. Si le fichier est remplacé
par une nouvelle version, il redevient candidat. La liste est conservée
entre deux lancements.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.core.models import Fingerprint, fingerprint


class IgnoreStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "ignored.json"
        self._lock = threading.Lock()
        self._items: dict[str, Fingerprint] = {}
        self._load()

    @staticmethod
    def _key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = {k: (int(v[0]), int(v[1])) for k, v in raw.items()}
        except (OSError, ValueError, TypeError, IndexError):
            self._items = {}
        self.prune()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._items), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # non bloquant : au pire, le fichier sera reproposé

    def add(self, path: Path) -> None:
        fp = fingerprint(path)
        if fp is None:
            return
        with self._lock:
            self._items[self._key(path)] = fp
            self._save()

    def contains(self, path: Path) -> bool:
        with self._lock:
            stored = self._items.get(self._key(path))
        if stored is None:
            return False
        if fingerprint(path) == stored:
            return True
        # Le fichier a changé : il redevient candidat.
        with self._lock:
            self._items.pop(self._key(path), None)
            self._save()
        return False

    def prune(self) -> None:
        """Oublie les fichiers qui n'existent plus."""
        with self._lock:
            self._items = {k: v for k, v in self._items.items() if os.path.exists(k)}
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._save()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

# GROGNON
