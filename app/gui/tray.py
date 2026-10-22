"""Icône dans la zone de notification (Windows, Linux).

pystray tourne dans son propre thread. Ses menus ne touchent jamais Tk
directement : ils déposent une fonction dans une file, que la fenêtre
principale exécute dans son propre thread (Tk n'est pas thread-safe).

Sous macOS, pystray et Tk veulent tous deux la boucle principale de
l'application : l'icône est désactivée et la fenêtre se réduit dans le Dock.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
from collections.abc import Callable

from app import APP_NAME

log = logging.getLogger(__name__)


def tray_supported() -> bool:
    return sys.platform != "darwin"


class TrayIcon:
    def __init__(
        self,
        ui_queue: "queue.Queue[Callable[[], None]]",
        *,
        on_open: Callable[[], None],
        on_toggle: Callable[[], None],
        is_watching: Callable[[], bool],
        pending_count: Callable[[], int],
        on_review: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._queue = ui_queue
        self._on_open = on_open
        self._on_toggle = on_toggle
        self._is_watching = is_watching
        self._pending = pending_count
        self._on_review = on_review
        self._on_quit = on_quit
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        try:
            import pystray

            from app.gui.icons import app_logo
        except Exception:  # noqa: BLE001 - pas de backend graphique disponible
            log.info("Zone de notification indisponible", exc_info=True)
            return False

        def later(fn: Callable[[], None]):
            return lambda *_: self._queue.put(fn)

        menu = pystray.Menu(
            pystray.MenuItem(f"Ouvrir {APP_NAME}", later(self._on_open), default=True),
            pystray.MenuItem(lambda _: f"À valider ({self._pending()})", later(self._on_review),
                             enabled=lambda _: self._pending() > 0),
            pystray.MenuItem("Surveillance active", later(self._on_toggle),
                             checked=lambda _: self._is_watching()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", later(self._on_quit)),
        )
        try:
            self._icon = pystray.Icon(APP_NAME, app_logo(64), APP_NAME, menu)
            self._thread = threading.Thread(target=self._icon.run, name="ordo-tray", daemon=True)
            self._thread.start()
        except Exception:  # noqa: BLE001
            log.info("Impossible de créer l'icône de notification", exc_info=True)
            self._icon = None
            return False
        return True

    def notify(self, title: str, message: str) -> None:
        if self._icon is not None:
            try:
                self._icon.notify(message, title)
            except Exception:  # noqa: BLE001
                log.debug("Notification pystray impossible", exc_info=True)

    def refresh(self) -> None:
        """Met à jour les libellés dynamiques du menu."""
        if self._icon is not None:
            try:
                self._icon.update_menu()
            except Exception:  # noqa: BLE001
                pass

    def set_title(self, text: str) -> None:
        if self._icon is not None:
            self._icon.title = text

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # noqa: BLE001
                pass
            self._icon = None

# GROGNON
