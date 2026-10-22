"""Point d'entrée d'Ordo.

    python main.py               # ouvre la fenêtre
    python main.py --minimized   # démarre dans la zone de notification (lancement auto)
    python main.py --debug       # journal détaillé
"""

from __future__ import annotations

import argparse
import logging
import sys

from app import APP_NAME, __version__
from app.config.settings import SettingsStore
from app.core.engine import Engine
from app.system.notifier import Notifier
from app.system.paths import data_dir, log_dir
from app.system.single_instance import SingleInstance
from app.utils.logger import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="Rangement automatique des téléchargements")
    parser.add_argument("--minimized", action="store_true", help="démarrer réduit dans la zone de notification")
    parser.add_argument("--debug", action="store_true", help="journal détaillé")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = parser.parse_args()

    log_file = setup_logging(log_dir(), args.debug)
    log = logging.getLogger("ordo")
    log.info("Démarrage de %s %s (journal : %s)", APP_NAME, __version__, log_file)

    lock = SingleInstance(data_dir())
    if not lock.acquire():
        log.warning("Une autre instance est déjà lancée")
        if not args.minimized:
            _already_running()
        return 1

    try:
        store = SettingsStore()
        settings = store.load()
        notifier = Notifier()
        engine = Engine(settings.copy(), data_dir(), notify=notifier)
        engine.start()

        from app.gui.app_window import AppWindow  # import tardif : Tk seulement si nécessaire

        window = AppWindow(settings, store, engine, notifier, start_minimized=args.minimized)
        window.mainloop()
        engine.shutdown()
    except Exception:
        log.exception("Erreur fatale")
        raise
    finally:
        lock.release()
    log.info("Arrêt de %s", APP_NAME)
    return 0


def _already_running() -> None:
    """Message simple quand l'application tourne déjà (souvent cachée dans la zone de notification)."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, f"{APP_NAME} est déjà ouvert.\n\n"
                                      "Cherchez son icône dans la zone de notification, près de l'horloge.")
        root.destroy()
    except Exception:  # noqa: BLE001
        print(f"{APP_NAME} est déjà ouvert.", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
