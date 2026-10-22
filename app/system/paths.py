"""Chemins standards de l'utilisateur et de l'application.

Les réglages stockent les dossiers avec des marqueurs portables
(``{downloads}``, ``{documents}``…) plutôt qu'en dur : le même fichier de
configuration reste valable sous Windows, macOS et Linux, et dans une langue
de système différente (``Téléchargements`` / ``Downloads``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import platformdirs

from app import APP_AUTHOR, APP_NAME


def standard_dirs() -> dict[str, Path]:
    """Dossiers personnels standards, résolus pour le système courant."""
    return {
        "home": Path.home(),
        "downloads": Path(platformdirs.user_downloads_dir()),
        "documents": Path(platformdirs.user_documents_dir()),
        "pictures": Path(platformdirs.user_pictures_dir()),
        "videos": Path(platformdirs.user_videos_dir()),
        "music": Path(platformdirs.user_music_dir()),
        "desktop": Path(platformdirs.user_desktop_dir()),
    }


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def expand_path(value: str) -> Path:
    """Transforme ``"{documents}/Ordo"`` en chemin absolu.

    Les marqueurs inconnus sont laissés tels quels, ``~`` et les variables
    d'environnement sont développés.
    """
    dirs = standard_dirs()

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return str(dirs[key]) if key in dirs else match.group(0)

    expanded = _PLACEHOLDER.sub(repl, value.strip())
    expanded = os.path.expandvars(os.path.expanduser(expanded))
    return Path(expanded)


def contract_path(path: Path | str) -> str:
    """Opération inverse, pour afficher un chemin court : ``~/Documents/Ordo``."""
    path = Path(path)
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def resource_path(relative: str) -> Path:
    """Fichier embarqué (icône…), que l'on soit lancé depuis les sources ou
    depuis un exécutable PyInstaller (qui décompresse dans ``sys._MEIPASS``)."""
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def config_dir() -> Path:
    path = Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = Path(platformdirs.user_log_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path
