"""Icônes dessinées avec Pillow : aucune image à distribuer, rendu net en HiDPI.

Chaque icône est dessinée en 4× puis réduite (anticrénelage), en deux
couleurs pour les thèmes clair et sombre.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw

from app.gui import theme

SCALE = 4


def _canvas(size: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), s


def _finish(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.LANCZOS)


def _draw(name: str, color: str, size: int) -> Image.Image:
    img, d, s = _canvas(size)
    w = max(SCALE * 2, int(s * 0.09))  # épaisseur du trait
    m = int(s * 0.14)                   # marge

    if name == "dashboard":  # quatre blocs, l'un plus haut
        g = int(s * 0.08)
        mid = s // 2
        d.rounded_rectangle([m, m, mid - g // 2, int(s * 0.58)], radius=w, outline=color, width=w)
        d.rounded_rectangle([mid + g // 2, m, s - m, int(s * 0.40)], radius=w, outline=color, width=w)
        d.rounded_rectangle([m, int(s * 0.58) + g, mid - g // 2, s - m], radius=w, outline=color, width=w)
        d.rounded_rectangle([mid + g // 2, int(s * 0.40) + g, s - m, s - m], radius=w, outline=color, width=w)
    elif name == "inbox":  # bac de réception
        d.rounded_rectangle([m, m, s - m, s - m], radius=w * 2, outline=color, width=w)
        y = int(s * 0.58)
        d.line([m, y, int(s * 0.36), y, int(s * 0.42), int(s * 0.70), int(s * 0.58), int(s * 0.70),
                int(s * 0.64), y, s - m, y], fill=color, width=w, joint="curve")
    elif name == "history":  # horloge
        d.ellipse([m, m, s - m, s - m], outline=color, width=w)
        c = s // 2
        d.line([c, c, c, int(s * 0.30)], fill=color, width=w)
        d.line([c, c, int(s * 0.66), int(s * 0.60)], fill=color, width=w)
    elif name == "settings":  # curseurs de réglage
        for i, knob in enumerate((0.32, 0.66, 0.44)):
            y = int(s * (0.26 + i * 0.24))
            d.line([m, y, s - m, y], fill=color, width=w)
            x = int(s * knob)
            r = int(s * 0.09)
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    elif name == "folder":
        d.rounded_rectangle([m, int(s * 0.30), s - m, s - m], radius=w, outline=color, width=w)
        d.line([m, int(s * 0.30), m, int(s * 0.22), int(s * 0.42), int(s * 0.22), int(s * 0.50), int(s * 0.30)],
               fill=color, width=w, joint="curve")
    elif name == "scan":  # loupe
        d.ellipse([m, m, int(s * 0.68), int(s * 0.68)], outline=color, width=w)
        d.line([int(s * 0.62), int(s * 0.62), s - m, s - m], fill=color, width=int(w * 1.3))
    elif name == "check":
        d.line([int(s * 0.20), int(s * 0.52), int(s * 0.42), int(s * 0.74), int(s * 0.80), int(s * 0.30)],
               fill=color, width=int(w * 1.2), joint="curve")
    elif name == "edit":  # crayon
        d.line([int(s * 0.26), int(s * 0.74), int(s * 0.74), int(s * 0.26)], fill=color, width=int(w * 1.6))
        d.polygon([(int(s * 0.18), int(s * 0.82)), (int(s * 0.22), int(s * 0.64)), (int(s * 0.36), int(s * 0.78))],
                  fill=color)
    elif name == "close":
        d.line([int(s * 0.28), int(s * 0.28), int(s * 0.72), int(s * 0.72)], fill=color, width=w)
        d.line([int(s * 0.72), int(s * 0.28), int(s * 0.28), int(s * 0.72)], fill=color, width=w)
    elif name == "undo":  # flèche de retour
        d.arc([int(s * 0.24), int(s * 0.30), int(s * 0.84), int(s * 0.82)], start=200, end=90, fill=color, width=w)
        d.polygon([(int(s * 0.14), int(s * 0.44)), (int(s * 0.38), int(s * 0.30)), (int(s * 0.36), int(s * 0.56))],
                  fill=color)
    return _finish(img, size)


@lru_cache(maxsize=None)
def icon(name: str, size: int = 18, color: tuple[str, str] = theme.MUTED) -> ctk.CTkImage:
    light = _draw(name, color[0], size)
    dark = _draw(name, color[1], size)
    return ctk.CTkImage(light_image=light, dark_image=dark, size=(size, size))


# --------------------------------------------------------------- logo

TAB_COLORS = ("#E9AE48", "#3CC48A", "#5B8CFF")


def app_logo(size: int = 256) -> Image.Image:
    """Logo : trois onglets de dossiers décalés sur fond ardoise."""
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill="#222838")
    left, right = int(s * 0.20), int(s * 0.80)
    for i, color in enumerate(TAB_COLORS):
        top = int(s * (0.24 + i * 0.17))
        tab_x = left + int(s * 0.12 * i)
        d.rounded_rectangle([tab_x, top, tab_x + int(s * 0.26), top + int(s * 0.12)],
                            radius=int(s * 0.03), fill=color)
        d.rounded_rectangle([left, top + int(s * 0.07), right, top + int(s * 0.24)],
                            radius=int(s * 0.035), fill=color)
    return img.resize((size, size), Image.LANCZOS)


def save_logo_files(directory: Path) -> tuple[Path, Path]:
    """Écrit ``icon.png`` et ``icon.ico`` (utilisés par PyInstaller)."""
    directory.mkdir(parents=True, exist_ok=True)
    png, ico = directory / "icon.png", directory / "icon.ico"
    logo = app_logo(512)
    logo.save(png)
    logo.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png, ico

# GROGNON
