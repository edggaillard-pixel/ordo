"""Exécution des propositions validées.

Entre la proposition et la validation, le disque a pu changer (un autre
fichier du même nom est arrivé, le fichier source a été modifié…). Tout est
donc revérifié juste avant d'agir.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import Settings
from app.core import conflicts
from app.core.journal import Journal
from app.core.models import ActionKind, ActionStatus, JournalEntry, PlannedAction, fingerprint
from app.core.planner import Planner
from app.fs import archives
from app.fs.file_ops import DestinationExists, safe_move, send_to_trash

log = logging.getLogger(__name__)


class SourceChanged(Exception):
    """Le fichier a changé depuis la proposition : il faut la recalculer."""


@dataclass
class ExecutionResult:
    action: PlannedAction
    entry: JournalEntry | None = None
    warning: str | None = None


class Executor:
    def __init__(self, settings: Settings, planner: Planner, journal: Journal) -> None:
        self.settings = settings
        self.planner = planner
        self.journal = journal

    def execute(self, action: PlannedAction, batch_id: str) -> ExecutionResult:
        source = action.source
        if not source.exists():
            raise FileNotFoundError(f"{source.name} n'est plus dans le dossier surveillé.")
        if action.source_fingerprint and fingerprint(source) != action.source_fingerprint and not action.is_dir:
            raise SourceChanged(f"{source.name} a été modifié depuis la proposition.")

        # Un fichier identique a pu être rangé entre-temps (deux copies du
        # même téléchargement validées ensemble, par exemple).
        if action.kind is ActionKind.MOVE and not action.user_edited:
            self.planner.check_duplicate(action)

        # Dernier contrôle de nom libre, puis déplacement. Si un fichier
        # apparaît au même nom pendant le déplacement, on recommence.
        for _ in range(5):
            action.new_name = conflicts.resolve_conflict(
                action.target_dir, action.new_name, is_dir=action.is_dir
            )
            try:
                safe_move(source, action.destination)
                break
            except DestinationExists:
                continue
        else:
            raise DestinationExists(str(action.destination))

        result = ExecutionResult(action)
        extracted: Path | None = None
        if action.extract_to is not None and action.kind is ActionKind.MOVE:
            extracted, result.warning = self._extract(action)

        action.status = ActionStatus.DONE
        result.entry = JournalEntry(
            batch_id=batch_id,
            action_id=action.id,
            timestamp=time.time(),
            kind=action.kind.value,
            category=action.category,
            source=str(source),
            destination=str(action.destination),
            extracted=str(extracted) if extracted else None,
        )
        self.journal.record(result.entry)
        return result

    def _extract(self, action: PlannedAction) -> tuple[Path | None, str | None]:
        """Décompresse l'archive rangée. Un échec n'annule pas le rangement."""
        assert action.extract_to is not None
        cfg = self.settings.archives
        target = action.extract_to.parent / conflicts.resolve_conflict(
            action.extract_to.parent, action.extract_to.name, is_dir=True
        )
        try:
            extracted = archives.extract(action.destination, target, cfg.max_extract_mb * 1024 * 1024)
        except (archives.ArchiveError, OSError) as exc:
            log.warning("Décompression impossible pour %s : %s", action.destination.name, exc)
            return None, f"Archive rangée mais non décompressée : {exc}"
        action.extract_to = extracted
        if cfg.trash_after_extract:
            try:
                send_to_trash(action.destination)
            except Exception as exc:  # noqa: BLE001
                log.warning("Impossible d'envoyer %s à la corbeille : %s", action.destination, exc)
        return extracted, None
