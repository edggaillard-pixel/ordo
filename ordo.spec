# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller pour Ordo.

    pyinstaller ordo.spec

- Windows : dist/Ordo.exe (un seul fichier, sans console)
- macOS   : dist/Ordo.app
- Linux   : dist/Ordo (un seul fichier)
"""

import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("customtkinter")  # thèmes et polices de CustomTkinter
datas += [("assets/icon.png", "assets"), ("assets/icon.ico", "assets")]

# Backends choisis à l'exécution selon le système : PyInstaller ne les voit pas seul.
hiddenimports = collect_submodules("watchdog.observers") + collect_submodules("pystray")

a = Analysis(
    ["main.py"],
    pathex=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "unittest", "pydoc", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # Sur macOS, un .app « onedir » démarre vite et passe mieux Gatekeeper.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Ordo", console=False,
              icon="assets/icon.png", argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="Ordo")
    app = BUNDLE(
        coll,
        name="Ordo.app",
        icon="assets/icon.png",  # converti en .icns automatiquement (Pillow requis)
        bundle_identifier="com.ordo.app",
        info_plist={
            "CFBundleName": "Ordo",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Ordo",
        },
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Ordo",
        console=False,          # pas de fenêtre noire
        icon="assets/icon.ico" if sys.platform == "win32" else None,
        upx=False,              # UPX déclenche souvent les antivirus
    )
