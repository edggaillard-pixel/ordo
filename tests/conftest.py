"""Fixtures communes : un faux dossier personnel dans un répertoire temporaire."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import Settings  # noqa: E402


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    (tmp_path / "Downloads").mkdir()
    return tmp_path


@pytest.fixture()
def settings(home: Path) -> Settings:
    """Réglages par défaut, mais avec tous les dossiers dans ``home``."""
    s = Settings()
    s.source_dir = str(home / "Downloads")
    s.stability_seconds = 0.6
    for cat in s.categories:
        cat.target = str(home / "Rangement" / cat.name)
    s.duplicates.folder = str(home / "Rangement" / "_Doublons")
    s.folders.target = str(home / "Rangement" / "Dossiers")
    s.archives.extract_to = str(home / "Rangement" / "Dossiers")
    return s


def make_file(path: Path, content: bytes | str = b"contenu", mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode() if isinstance(content, str) else content
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def wait_until(predicate, timeout: float = 10.0, step: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()
