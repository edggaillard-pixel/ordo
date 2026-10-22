"""Moteur : orchestre surveillance, planification, validation et exécution.

Threads
-------
- **watchdog** : signale les entrées qui apparaissent dans le dossier source ;
- **worker** (un seul) : fait TOUT le travail sur le disque, dans l'ordre.
  Un thread unique évite que deux fichiers arrivés en même temps sous le même
  nom se disputent la même destination ;
- **GUI** : n'appelle que les méthodes publiques ci-dessous, qui déposent des
  commandes dans une file. Elle lit les résultats dans ``engine.events``.

Le worker tourne en permanence, même surveillance coupée : on peut toujours
valider la liste d'attente, analyser le dossier ou annuler un lot.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.settings import MODE_AUTO, Settings
from app.core.executor import Executor, SourceChanged
from app.core.ignore_store import IgnoreStore
from app.core.journal import Journal
from app.core.models import ActionKind, PlannedAction, fingerprint
from app.core.planner import Planner
from app.core.stability import StabilityTracker, has_temp_sibling, is_unlocked
from app.core.watcher import SourceWatcher

log = logging.getLogger(__name__)

TICK_SECONDS = 0.4
RESCAN_EVERY = 30.0       # filet de sécurité si watchdog rate un événement
PRUNE_EVERY = 3.0         # nettoyage de la liste d'attente
NOTIFY_QUIET = 2.0        # regroupe les notifications rapprochées


# ---------------------------------------------------------------------------
# Événements publiés vers l'interface
# ---------------------------------------------------------------------------

@dataclass
class EngineEvent:
    kind: str  # status | pending | activity | history | stats | scan | error
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Activity:
    timestamp: float
    level: str        # "success", "info", "warning", "error"
    message: str
    category: str | None = None
    path: str | None = None


@dataclass
class Stats:
    sorted_today: int = 0
    duplicates_today: int = 0
    errors: int = 0


Notify = Callable[[str, str], None]


# ---------------------------------------------------------------------------
# Moteur
# ---------------------------------------------------------------------------

class Engine:
    def __init__(self, settings: Settings, data_dir: Path, notify: Notify | None = None) -> None:
        self.settings = settings
        self.journal = Journal(data_dir)
        self.ignored = IgnoreStore(data_dir)
        self.events: queue.Queue[EngineEvent] = queue.Queue()
        self.recent: deque[Activity] = deque(maxlen=200)
        self.stats = Stats()
        self.notify = notify

        self._planner = Planner(settings)
        self._executor = Executor(settings, self._planner, self.journal)
        self._tracker = StabilityTracker(settings.stability_seconds, settings.temp_extensions)
        self._commands: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self._pending: OrderedDict[str, PlannedAction] = OrderedDict()
        self._pending_lock = threading.RLock()
        self._watcher: SourceWatcher | None = None
        self._baseline: set[str] = set()       # entrées déjà là au démarrage
        self._left_in_place: dict[str, Any] = {}
        self._notifications: list[tuple[str, str]] = []
        self._last_notification_input = 0.0
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._last_rescan = 0.0
        self._last_prune = 0.0
        self._load_today_stats()

    # ================================================================ API

    def start(self) -> None:
        """Démarre le thread de traitement (pas la surveillance)."""
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="ordo-worker", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._commands.put(("stop_watching", ()))
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=5)
        self._flush_notifications(force=True)

    @property
    def watching(self) -> bool:
        return self._watcher is not None

    def set_watching(self, enabled: bool) -> None:
        self._commands.put(("start_watching" if enabled else "stop_watching", ()))

    def apply_settings(self, settings: Settings) -> None:
        self._commands.put(("apply_settings", (settings,)))

    def scan_now(self) -> None:
        self._commands.put(("scan", ()))

    def approve(self, action_ids: Iterable[str]) -> None:
        self._commands.put(("approve", (list(action_ids),)))

    def reject(self, action_ids: Iterable[str]) -> None:
        self._commands.put(("reject", (list(action_ids),)))

    def undo(self, batch_id: str) -> None:
        self._commands.put(("undo", (batch_id,)))

    def clear_ignored(self) -> None:
        self._commands.put(("clear_ignored", ()))

    def pending(self) -> list[PlannedAction]:
        """Copie de la liste d'attente (lecture sans risque depuis la GUI)."""
        import copy

        with self._pending_lock:
            return [copy.copy(a) for a in self._pending.values()]

    def pending_count(self) -> int:
        with self._pending_lock:
            return len(self._pending)

    def update_pending(
        self,
        action_id: str,
        *,
        new_name: str | None = None,
        category: str | None = None,
        target_dir: Path | None = None,
    ) -> PlannedAction | None:
        """Modification manuelle d'une proposition depuis l'écran de validation."""
        with self._pending_lock:
            action = self._pending.get(action_id)
            if action is None:
                return None
            if category and category != action.category:
                self._planner.retarget(action, category)
            if target_dir is not None:
                action.target_dir = Path(target_dir)
            if new_name:
                action.new_name = new_name.strip()
            action.user_edited = True
            action.error = None
        self._emit("pending", count=self.pending_count())
        return action

    def preview_category(self, action_id: str, category: str) -> Path | None:
        """Dossier cible qu'aurait la proposition avec une autre catégorie."""
        with self._pending_lock:
            action = self._pending.get(action_id)
        if action is None:
            return None
        import copy

        probe = copy.copy(action)
        self._planner.retarget(probe, category)
        return probe.target_dir

    # ============================================================ worker

    def _run(self) -> None:
        while self._running.is_set():
            try:
                name, args = self._commands.get(timeout=TICK_SECONDS)
                self._handle_command(name, args)
                continue  # vider d'abord toutes les commandes en attente
            except queue.Empty:
                pass
            except Exception:  # noqa: BLE001 - le worker ne doit jamais mourir
                log.exception("Erreur inattendue dans le moteur")
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                log.exception("Erreur inattendue dans le moteur")
        self._stop_watching()

    def _handle_command(self, name: str, args: tuple) -> None:
        handler = getattr(self, f"_cmd_{name}")
        handler(*args)

    def _tick(self) -> None:
        now = time.monotonic()
        if self._watcher is not None:
            ready = self._tracker.poll()
            if ready:
                self._process_ready(ready)
            if now - self._last_rescan >= RESCAN_EVERY:
                self._last_rescan = now
                self._rescan()
        if now - self._last_prune >= PRUNE_EVERY:
            self._last_prune = now
            self._prune_pending()
        self._flush_notifications()

    # ------------------------------------------------------- surveillance

    def _cmd_start_watching(self) -> None:
        if self._watcher is not None:
            return
        source = self.settings.source_path
        if not source.is_dir():
            self._activity("error", f"Dossier surveillé introuvable : {source}")
            self._emit("status", watching=False, error=f"Dossier introuvable : {source}")
            return
        # Ce qui est déjà là n'est pas touché (sauf via « Analyser le dossier »).
        self._baseline = {self._key(p) for p in self._list_source()}
        try:
            watcher = SourceWatcher(source, self._tracker.touch)
            watcher.start()
        except Exception as exc:  # noqa: BLE001 - quota inotify, droits…
            log.exception("Impossible de démarrer la surveillance")
            self._emit("status", watching=False, error=str(exc))
            return
        self._watcher = watcher
        self._last_rescan = time.monotonic()
        self._activity("info", f"Surveillance activée sur {source}")
        self._emit("status", watching=True)

    def _cmd_stop_watching(self) -> None:
        if self._watcher is None:
            return
        self._stop_watching()
        self._activity("info", "Surveillance mise en pause")
        self._emit("status", watching=False)

    def _stop_watching(self) -> None:
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:  # noqa: BLE001
                log.exception("Arrêt de la surveillance")
        self._watcher = None
        self._tracker.clear()

    def _rescan(self) -> None:
        """Filet de sécurité : rattrape les entrées que watchdog n'a pas vues."""
        entries = self._list_source()
        present = {self._key(p) for p in entries}
        self._baseline &= present  # un fichier supprimé puis recréé redevient nouveau
        for path in entries:
            if self._key(path) not in self._baseline and not self._is_pending(path):
                self._tracker.touch(path)

    def _list_source(self) -> list[Path]:
        try:
            with os.scandir(self.settings.source_path) as it:
                return [Path(e.path) for e in it]
        except OSError:
            return []

    # --------------------------------------------------------- traitement

    def _process_ready(self, paths: Iterable[Path], from_scan: bool = False) -> int:
        """Planifie les entrées prêtes ; les range directement en mode auto."""
        to_execute: list[PlannedAction] = []
        added = 0
        for path in paths:
            key = self._key(path)
            if not from_scan and key in self._baseline:
                continue
            if self.ignored.contains(path) or self._planner.should_ignore(path):
                continue
            existing = self._find_pending(path)
            if existing is not None:
                if existing.source_fingerprint == fingerprint(path) or existing.is_dir:
                    continue
                self._remove_pending([existing.id])  # nouvelle version du fichier

            try:
                action = self._planner.plan(path, reserved=self._reserved_destinations())
            except OSError as exc:
                self._activity("error", f"{path.name} : lecture impossible ({exc})", path=str(path))
                continue

            if action is None:
                fp = fingerprint(path)
                if self._left_in_place.get(key) != fp:
                    self._left_in_place[key] = fp
                    self._activity("info", f"{path.name} : aucune règle, laissé en place", path=str(path))
                continue

            action.from_scan = from_scan
            if self.settings.mode == MODE_AUTO and not from_scan:
                to_execute.append(action)
            else:
                with self._pending_lock:
                    self._pending[action.id] = action
                added += 1

        if added:
            self._emit("pending", count=self.pending_count())
            if not from_scan:
                self._queue_notification("review", f"{added}")
        if to_execute:
            self._execute(to_execute)
        return added

    def _cmd_scan(self) -> None:
        """« Analyser le dossier » : tout ce qui est présent passe en validation."""
        candidates: list[Path] = []
        temp = self.settings.temp_extensions
        for path in self._list_source():
            if self._is_pending(path):
                continue
            if not path.is_dir() and (has_temp_sibling(path, temp) or not is_unlocked(path)):
                continue  # encore en cours de téléchargement
            candidates.append(path)
        added = self._process_ready(candidates, from_scan=True)
        self._activity("info", f"Analyse terminée : {added} proposition(s) ajoutée(s) à la validation")
        self._emit("scan", added=added)

    def _cmd_approve(self, action_ids: list[str]) -> None:
        with self._pending_lock:
            actions = [self._pending[i] for i in action_ids if i in self._pending]
        self._execute(actions)

    def _execute(self, actions: list[PlannedAction]) -> None:
        if not actions:
            return
        batch_id = uuid.uuid4().hex[:12]
        done = 0
        last_done: PlannedAction | None = None
        for action in actions:
            try:
                result = self._executor.execute(action, batch_id)
            except SourceChanged as exc:
                self._remove_pending([action.id])
                self._activity("warning", f"{exc} Proposition recalculée.", path=str(action.source))
                # Le fichier est peut-être encore en cours d'écriture : on le
                # repasse par le suivi de stabilité si la surveillance tourne.
                if self._watcher is not None and not action.from_scan:
                    self._tracker.touch(action.source)
                else:
                    self._process_ready([action.source], from_scan=True)
                continue
            except FileNotFoundError as exc:
                self._remove_pending([action.id])
                self._activity("warning", str(exc), path=str(action.source))
                continue
            except Exception as exc:  # noqa: BLE001
                self.stats.errors += 1
                with self._pending_lock:
                    if action.id in self._pending:
                        self._pending[action.id].error = str(exc)
                    elif not action.from_scan:
                        # mode auto : l'échec rejoint la liste d'attente
                        action.error = str(exc)
                        self._pending[action.id] = action
                self._activity("error", f"{action.source.name} : {exc}", path=str(action.source))
                self._queue_notification("error", action.source.name)
                continue

            self._remove_pending([action.id], emit=False)
            done += 1
            last_done = action
            if action.kind is ActionKind.DUPLICATE:
                self.stats.duplicates_today += 1
                self._activity(
                    "warning",
                    f"{action.original_name} est un doublon de {action.duplicate_of.name if action.duplicate_of else '?'} → {action.target_dir.name}",
                    category=action.category, path=str(action.destination),
                )
            else:
                self.stats.sorted_today += 1
                message = f"{action.original_name} → {action.category} / {action.new_name}"
                self._activity("success", message, category=action.category, path=str(action.destination))
            if result.warning:
                self._activity("warning", result.warning, path=str(action.destination))
            elif action.extract_to is not None and result.entry and result.entry.extracted:
                self._activity("info", f"Archive décompressée dans {Path(result.entry.extracted).name}",
                               path=result.entry.extracted)

        self._emit("pending", count=self.pending_count())
        self._emit("stats")
        if done:
            self._emit("history")
            if done == 1 and last_done is not None:
                self._queue_notification("done", f"{last_done.new_name} → {last_done.category}")
            else:
                self._queue_notification("done", f"{done} fichiers rangés")

    def _cmd_reject(self, action_ids: list[str]) -> None:
        with self._pending_lock:
            actions = [self._pending[i] for i in action_ids if i in self._pending]
        for action in actions:
            self.ignored.add(action.source)
        self._remove_pending([a.id for a in actions])
        if actions:
            label = actions[0].original_name if len(actions) == 1 else f"{len(actions)} fichiers"
            self._activity("info", f"{label} : ignoré(s), ne sera plus proposé tant qu'il ne change pas")

    def _cmd_undo(self, batch_id: str) -> None:
        result = self.journal.undo_batch(batch_id)
        for _, restored in result.restored:
            # Le fichier revient dans le dossier surveillé : on ne doit pas le
            # ranger de nouveau aussitôt.
            self.ignored.add(restored)
        if result.restored:
            self.stats.sorted_today = max(0, self.stats.sorted_today - len(result.restored))
            self._activity("info", f"Annulation : {len(result.restored)} élément(s) remis à leur place")
        for error in result.errors:
            self._activity("error", f"Annulation : {error}")
        self._emit("history")
        self._emit("stats")

    def _cmd_clear_ignored(self) -> None:
        self.ignored.clear()
        self._activity("info", "Liste des fichiers ignorés vidée")
        self._emit("stats")

    def _cmd_apply_settings(self, settings: Settings) -> None:
        old_source = self.settings.source_path
        self.settings = settings
        self._planner = Planner(settings)
        self._executor = Executor(settings, self._planner, self.journal)
        self._tracker.stable_seconds = settings.stability_seconds
        self._tracker.temp_extensions = list(settings.temp_extensions)

        # Les propositions non modifiées à la main suivent les nouvelles règles.
        with self._pending_lock:
            stale = [a for a in self._pending.values() if not a.user_edited]
        for action in stale:
            self._remove_pending([action.id], emit=False)
        if stale:
            self._process_ready([a.source for a in stale], from_scan=True)
        if self.settings.source_path != old_source and self._watcher is not None:
            self._stop_watching()
            self._cmd_start_watching()
        self._activity("info", "Réglages enregistrés")
        self._emit("pending", count=self.pending_count())

    # ---------------------------------------------------- liste d'attente

    def _prune_pending(self) -> None:
        """Retire les propositions dont le fichier a disparu."""
        with self._pending_lock:
            gone = [a.id for a in self._pending.values() if not a.source.exists()]
        if gone:
            self._remove_pending(gone)

    def _remove_pending(self, ids: Iterable[str], emit: bool = True) -> None:
        with self._pending_lock:
            for action_id in ids:
                self._pending.pop(action_id, None)
        if emit:
            self._emit("pending", count=self.pending_count())

    def _find_pending(self, path: Path) -> PlannedAction | None:
        key = self._key(path)
        with self._pending_lock:
            for action in self._pending.values():
                if self._key(action.source) == key:
                    return action
        return None

    def _is_pending(self, path: Path) -> bool:
        return self._find_pending(path) is not None

    def _reserved_destinations(self) -> list[Path]:
        with self._pending_lock:
            return [a.destination for a in self._pending.values()]

    # ------------------------------------------------------- utilitaires

    @staticmethod
    def _key(path: Path) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _load_today_stats(self) -> None:
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        for entry in self.journal.entries_since(midnight):
            if entry.undone:
                continue
            if entry.kind == ActionKind.DUPLICATE.value:
                self.stats.duplicates_today += 1
            else:
                self.stats.sorted_today += 1

    def _activity(self, level: str, message: str, category: str | None = None, path: str | None = None) -> None:
        item = Activity(time.time(), level, message, category, path)
        self.recent.appendleft(item)
        getattr(log, "error" if level == "error" else "warning" if level == "warning" else "info")(message)
        self._emit("activity", item=item)

    def _emit(self, kind: str, **data: Any) -> None:
        self.events.put(EngineEvent(kind, data))

    # ------------------------------------------------------ notifications

    def _queue_notification(self, kind: str, detail: str) -> None:
        if not self.settings.notifications or self.notify is None:
            return
        self._notifications.append((kind, detail))
        self._last_notification_input = time.monotonic()

    def _flush_notifications(self, force: bool = False) -> None:
        """Envoie une seule notification résumant les dernières secondes."""
        if not self._notifications or self.notify is None:
            return
        if not force and time.monotonic() - self._last_notification_input < NOTIFY_QUIET:
            return
        items, self._notifications = self._notifications, []
        review = sum(int(d) for k, d in items if k == "review")
        done = [d for k, d in items if k == "done"]
        errors = [d for k, d in items if k == "error"]
        lines: list[str] = []
        if review:
            lines.append(f"{review} fichier(s) à valider")
        if done:
            lines.append(done[0] if len(done) == 1 else f"{len(done)} rangements effectués")
        if errors:
            lines.append(f"Échec : {', '.join(errors[:3])}" + ("…" if len(errors) > 3 else ""))
        title = "Ordo — action requise" if review or errors else "Ordo — fichiers rangés"
        try:
            self.notify(title, "\n".join(lines))
        except Exception:  # noqa: BLE001 - une notification ratée n'est pas grave
            log.debug("Notification impossible", exc_info=True)

# GROGNON
