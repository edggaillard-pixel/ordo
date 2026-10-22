"""Journalisation dans un fichier tournant (3 × 1 Mo) et sur la console."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(directory: Path, debug: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "ordo.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s", "%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Pas de console dans un exécutable « fenêtré » : sys.stderr vaut None.
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)

    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    return log_file
