"""Journal des opérations et annulation.

Chaque déplacement effectué est ajouté à ``journal.jsonl`` (une ligne JSON par
opération, en ajout seul : un plantage ne peut perdre que la dernière ligne).
Les opérations validées ensemble forment un *lot*, annulable d'un clic depuis
l'écran Historique.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path

from app.core.conflicts import resolve_conflict
from app.core.models import Batch, JournalEntry
from app.fs.file_ops import safe_move, send_to_trash

log = logging.getLogger(__name__)

MAX_BATCHES = 500


class UndoResult:
    def __init__(self) -> None:
        self.restored: list[tuple[Path, Path]] = []  # (ancien emplacement, restauré vers)
        self.errors: list[str] = []


class Journal:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "journal.jsonl"
        self._lock = threading.Lock()
        self._entries: list[JournalEntry] = []
        self._load()

    # ----------------------------------------------------------- lecture

    def _load(self) -> None:
        if not self.path.exists():
            return
        undone: set[str] = set()
        entries: list[JournalEntry] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            log.error("Journal illisible : %s", exc)
            return
        for line in lines:
            try:
                data = json.loads(line)
            except ValueError:
                continue  # ligne tronquée par un arrêt brutal
            if data.get("type") == "undo":
                undone.add(data["action_id"])
            elif data.get("type") == "entry":
                data.pop("type")
                try:
                    entries.append(JournalEntry(**data))
                except TypeError:
                    continue
        for entry in entries:
            entry.undone = entry.action_id in undone
        self._entries = entries
        self._compact()

    def batches(self, limit: int = 100) -> list[Batch]:
        """Lots du plus récent au plus ancien."""
        with self._lock:
            grouped: dict[str, list[JournalEntry]] = {}
            for entry in self._entries:
                grouped.setdefault(entry.batch_id, []).append(entry)
        result = [Batch(bid, entries[0].timestamp, entries) for bid, entries in grouped.items()]
        result.sort(key=lambda b: b.timestamp, reverse=True)
        return result[:limit]

    def entries_since(self, timestamp: float) -> list[JournalEntry]:
        with self._lock:
            return [e for e in self._entries if e.timestamp >= timestamp]

    # ----------------------------------------------------------- écriture

    def record(self, entry: JournalEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            self._append({"type": "entry", **asdict(entry)})

    def _append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _compact(self) -> None:
        """Ne garde que les MAX_BATCHES derniers lots (au démarrage)."""
        batch_ids: list[str] = []
        for entry in self._entries:
            if entry.batch_id not in batch_ids:
                batch_ids.append(entry.batch_id)
        if len(batch_ids) <= MAX_BATCHES:
            return
        keep = set(batch_ids[-MAX_BATCHES:])
        self._entries = [e for e in self._entries if e.batch_id in keep]
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps({"type": "entry", **asdict(entry)}, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)

    # ----------------------------------------------------------- annulation

    def undo_batch(self, batch_id: str) -> UndoResult:
        """Remet chaque fichier du lot à son emplacement d'origine.

        Si un fichier a été recréé entre-temps à l'emplacement d'origine, le
        fichier restauré reçoit un suffixe horodaté : rien n'est écrasé. Les
        dossiers créés par décompression partent à la corbeille.
        """
        result = UndoResult()
        with self._lock:
            entries = [e for e in self._entries if e.batch_id == batch_id and not e.undone]

        for entry in reversed(entries):
            try:
                if entry.extracted and Path(entry.extracted).exists():
                    send_to_trash(Path(entry.extracted))
                current = entry.destination_path
                if not current.exists():
                    raise FileNotFoundError(f"{current.name} n'est plus à l'emplacement où il a été rangé.")
                origin = entry.source_path
                name = resolve_conflict(origin.parent, origin.name, is_dir=current.is_dir())
                restored = safe_move(current, origin.parent / name)
                result.restored.append((current, restored))
                self._mark_undone(entry)
                _remove_empty_parents(current.parent)
            except Exception as exc:  # noqa: BLE001 - on continue le lot
                log.warning("Annulation impossible pour %s : %s", entry.destination, exc)
                result.errors.append(f"{Path(entry.destination).name} : {exc}")
        return result

    def _mark_undone(self, entry: JournalEntry) -> None:
        with self._lock:
            entry.undone = True
            self._append({"type": "undo", "action_id": entry.action_id, "timestamp": time.time()})


def _remove_empty_parents(folder: Path, depth: int = 2) -> None:
    """Supprime les sous-dossiers devenus vides (ex. « 2026/10 ») après annulation.

    Les dossiers personnels standards (Images, Documents…) ne sont jamais
    supprimés, même vides.
    """
    from app.system.paths import standard_dirs

    protected = {os.path.normcase(str(p)) for p in standard_dirs().values()}
    for _ in range(depth):
        if os.path.normcase(str(folder)) in protected:
            return
        try:
            folder.rmdir()  # échoue si le dossier n'est pas vide : c'est voulu
        except OSError:
            return
        folder = folder.parent
