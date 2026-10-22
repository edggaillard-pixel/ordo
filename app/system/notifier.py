"""Notifications système, sans dépendance lourde.

- Windows : bulle / toast de l'icône de la zone de notification (pystray) ;
- macOS   : ``osascript`` (Centre de notifications) ;
- Linux   : ``notify-send`` (libnotify), sinon l'icône pystray.

Si rien n'est disponible, la notification est simplement journalisée.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self) -> None:
        # Fonction fournie par l'icône de la zone de notification, si présente.
        self.tray_notify: Callable[[str, str], None] | None = None

    def __call__(self, title: str, message: str) -> None:
        self.notify(title, message)

    def notify(self, title: str, message: str) -> None:
        try:
            if sys.platform == "darwin":
                self._macos(title, message)
            elif sys.platform.startswith("linux") and shutil.which("notify-send"):
                subprocess.Popen(
                    ["notify-send", "--app-name=Ordo", title, message],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif self.tray_notify is not None:
                self.tray_notify(title, message)
            else:
                log.info("Notification : %s — %s", title, message)
        except Exception:  # noqa: BLE001
            log.debug("Échec de la notification", exc_info=True)

    @staticmethod
    def _macos(title: str, message: str) -> None:
        def esc(text: str) -> str:
            return text.replace("\\", "\\\\").replace('"', '\\"')

        script = f'display notification "{esc(message)}" with title "{esc(title)}"'
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
