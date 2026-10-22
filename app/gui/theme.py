"""Identité visuelle : couleurs, typographie, espacements.

Parti pris : l'application parle de classement, comme un meuble à dossiers
suspendus. Chaque catégorie a sa couleur d'onglet, reprise partout (liste à
valider, historique, réglages) sous forme d'un liseré vertical à gauche de la
ligne. C'est le seul élément de couleur vive de l'interface ; tout le reste
reste sobre (ardoise bleutée en sombre, gris perle en clair).

Chaque couleur est un couple (clair, sombre), format natif de CustomTkinter.
"""

from __future__ import annotations

import sys
from functools import lru_cache

import customtkinter as ctk

# --------------------------------------------------------------- couleurs

BG = ("#EEF1F6", "#1A1F2B")          # fond de fenêtre
SIDEBAR = ("#E3E8F0", "#151A24")     # barre latérale
PANEL = ("#FFFFFF", "#222838")       # surfaces de contenu
RAISED = ("#F5F7FB", "#2A3142")      # survol, champs
LINE = ("#D9DEE7", "#343C50")        # filets de séparation
TEXT = ("#1B2130", "#E6E9F0")
MUTED = ("#5E687C", "#9AA3B5")
FAINT = ("#8A93A5", "#6D7689")

ACCENT = ("#3D6BEB", "#5B8CFF")      # action principale
ACCENT_HOVER = ("#2F59CF", "#4A79EC")
ACCENT_SOFT = ("#E2EAFD", "#2B3757")  # fond des éléments sélectionnés

SUCCESS = ("#1F9D67", "#3CC48A")
WARNING = ("#B97A12", "#E9AE48")
DANGER = ("#C8423B", "#EE6B63")
DANGER_HOVER = ("#AD3630", "#D85B54")

LEVEL_COLORS = {"success": SUCCESS, "info": MUTED, "warning": WARNING, "error": DANGER}

# --------------------------------------------------------------- espacements

PAD = 24       # marge des écrans
GAP = 12       # écart entre blocs
RADIUS = 10    # surfaces
RADIUS_SM = 6  # boutons, champs


# --------------------------------------------------------------- typographie

@lru_cache(maxsize=1)
def _family() -> str:
    """Police d'interface native du système, pour une application qui s'y fond."""
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return "Helvetica Neue"
    import tkinter.font

    available = set(tkinter.font.families())
    for name in ("Inter", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans"):
        if name in available:
            return name
    return "TkDefaultFont"


@lru_cache(maxsize=None)
def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """Police mise en cache (une fenêtre Tk doit exister avant le premier appel)."""
    return ctk.CTkFont(family=_family(), size=size, weight=weight)


# Échelle typographique (rapport ≈ 1,2).
def title() -> ctk.CTkFont:
    return font(22, "bold")


def heading() -> ctk.CTkFont:
    return font(15, "bold")


def body() -> ctk.CTkFont:
    return font(13)


def body_bold() -> ctk.CTkFont:
    return font(13, "bold")


def small() -> ctk.CTkFont:
    return font(11)


def figure() -> ctk.CTkFont:
    return font(26, "bold")


def resolve(color: tuple[str, str] | str) -> str:
    """Couleur effective selon le thème courant (pour Pillow ou Tk brut)."""
    if isinstance(color, str):
        return color
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]

# GROGNON
