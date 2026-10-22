"""Objets métier échangés entre le moteur et l'interface."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ActionKind(str, Enum):
    MOVE = "move"            # fichier rangé dans sa catégorie
    DUPLICATE = "duplicate"  # contenu identique déjà présent → dossier des doublons
    FOLDER = "folder"        # dossier entrant déplacé tel quel


class ActionStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


Fingerprint = tuple[int, int]  # (taille en octets, date de modification en ns)


def fingerprint(path: Path) -> Fingerprint | None:
    """Empreinte légère d'un fichier, pour savoir s'il a changé depuis."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


@dataclass
class PlannedAction:
    """Ce que le moteur propose de faire pour une entrée du dossier surveillé.

    En mode « validation », ces propositions s'affichent dans l'écran
    *À valider*, où l'utilisateur peut les modifier ou les refuser.
    """

    source: Path
    kind: ActionKind
    target_dir: Path
    new_name: str
    category: str | None = None
    rule: str | None = None
    duplicate_of: Path | None = None
    extract_to: Path | None = None      # archive à décompresser après rangement
    source_fingerprint: Fingerprint | None = None
    user_edited: bool = False
    status: ActionStatus = ActionStatus.PENDING
    error: str | None = None
    from_scan: bool = False             # trouvé par « Analyser le dossier »
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)

    @property
    def destination(self) -> Path:
        return self.target_dir / self.new_name

    @property
    def original_name(self) -> str:
        return self.source.name

    @property
    def is_dir(self) -> bool:
        return self.kind is ActionKind.FOLDER

    @property
    def renamed(self) -> bool:
        return self.new_name != self.source.name


@dataclass
class JournalEntry:
    """Une opération réellement effectuée, gardée pour pouvoir l'annuler."""

    batch_id: str
    action_id: str
    timestamp: float
    kind: str
    category: str | None
    source: str
    destination: str
    extracted: str | None = None
    undone: bool = False

    @property
    def source_path(self) -> Path:
        return Path(self.source)

    @property
    def destination_path(self) -> Path:
        return Path(self.destination)


@dataclass
class Batch:
    """Groupe d'opérations validées ensemble (un clic sur « Valider »)."""

    id: str
    timestamp: float
    entries: list[JournalEntry]

    @property
    def undone(self) -> bool:
        return all(e.undone for e in self.entries)

    @property
    def size(self) -> int:
        return len(self.entries)


def same_path(a: Path, b: Path) -> bool:
    """Compare deux chemins en tenant compte de la casse du système."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
