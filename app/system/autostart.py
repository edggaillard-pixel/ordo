"""Lancement automatique à l'ouverture de session.

- Windows : clé ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` ;
- macOS   : LaunchAgent dans ``~/Library/LaunchAgents`` ;
- Linux   : fichier ``.desktop`` dans ``~/.config/autostart`` (norme XDG).

L'application est lancée avec ``--minimized`` : elle démarre directement dans
la zone de notification, surveillance active.
"""

from __future__ import annotations

import logging
import os
import plistlib
import shlex
import sys
from pathlib import Path

from app import APP_ID, APP_NAME

log = logging.getLogger(__name__)


def launch_command() -> list[str]:
    """Commande qui relance l'application dans son état actuel."""
    if getattr(sys, "frozen", False):  # exécutable PyInstaller
        return [sys.executable, "--minimized"]
    main = Path(__file__).resolve().parents[2] / "main.py"
    python = sys.executable
    if sys.platform == "win32":  # pythonw.exe : pas de console noire
        pythonw = Path(python).with_name("pythonw.exe")
        if pythonw.exists():
            python = str(pythonw)
    return [python, str(main), "--minimized"]


def set_enabled(enabled: bool) -> None:
    if sys.platform == "win32":
        _windows(enabled)
    elif sys.platform == "darwin":
        _macos(enabled)
    else:
        _linux(enabled)
    log.info("Démarrage automatique %s", "activé" if enabled else "désactivé")


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_plist().exists()
    return _linux_desktop().exists()


# ----------------------------------------------------------------- Windows

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows(enabled: bool) -> None:
    import subprocess
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(launch_command()))
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ------------------------------------------------------------------- macOS

def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def _macos(enabled: bool) -> None:
    plist = _mac_plist()
    if not enabled:
        plist.unlink(missing_ok=True)
        return
    plist.parent.mkdir(parents=True, exist_ok=True)
    with plist.open("wb") as fh:
        plistlib.dump(
            {"Label": APP_ID, "ProgramArguments": launch_command(), "RunAtLoad": True, "ProcessType": "Interactive"},
            fh,
        )


# ------------------------------------------------------------------- Linux

def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "ordo.desktop"


def _linux(enabled: bool) -> None:
    desktop = _linux_desktop()
    if not enabled:
        desktop.unlink(missing_ok=True)
        return
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Rangement automatique des téléchargements\n"
        f"Exec={shlex.join(launch_command())}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n",
        encoding="utf-8",
    )

# GROGNON
