"""Tableau de bord : état de la surveillance, chiffres du jour, activité récente."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.config.settings import MODE_AUTO
from app.core.engine import Activity
from app.fs.file_ops import open_in_file_manager
from app.gui import theme
from app.gui.widgets import Panel, Tab, ghost_button, label, primary_button, secondary_button
from app.system.paths import contract_path

if TYPE_CHECKING:
    from app.gui.app_window import AppWindow

MAX_ROWS = 60


class DashboardView(ctk.CTkFrame):
    def __init__(self, master, app: "AppWindow") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- En-tête -------------------------------------------------------
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD, 4))
        head.grid_columnconfigure(0, weight=1)
        label(head, "Tableau de bord", "title").grid(row=0, column=0, sticky="w")
        secondary_button(head, "Ouvrir le dossier", self._open_source, icon="folder").grid(
            row=0, column=1, padx=(0, 8))
        primary_button(head, "Analyser le dossier", self.app.engine.scan_now, width=170).grid(row=0, column=2)

        self.source_label = label(self, "", "body", theme.MUTED)
        self.source_label.grid(row=1, column=0, sticky="w", padx=theme.PAD)

        # --- Bandeau d'état + chiffres --------------------------------------
        summary = Panel(self)
        summary.grid(row=2, column=0, sticky="ew", padx=theme.PAD, pady=(18, theme.GAP))
        for col in range(4):
            summary.grid_columnconfigure(col, weight=1, uniform="figures")

        self.figures: dict[str, ctk.CTkLabel] = {}
        specs = [
            ("sorted", "rangés aujourd'hui", theme.TEXT),
            ("pending", "en attente de validation", theme.ACCENT),
            ("duplicates", "doublons écartés", theme.WARNING),
            ("errors", "erreurs depuis le lancement", theme.DANGER),
        ]
        for col, (key, caption, color) in enumerate(specs):
            cell = ctk.CTkFrame(summary, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="nsew", padx=(20, 0) if col == 0 else 0, pady=16)
            if col:
                ctk.CTkFrame(summary, width=1, fg_color=theme.LINE).grid(row=0, column=col, sticky="nsw", pady=14)
                cell.grid_configure(padx=(20, 0))
            self.figures[key] = label(cell, "0", "figure", color)
            self.figures[key].pack(anchor="w")
            label(cell, caption, "small", theme.MUTED).pack(anchor="w")

        # Bandeau d'invitation quand des fichiers attendent.
        self.review_banner = ctk.CTkFrame(summary, fg_color=theme.ACCENT_SOFT, corner_radius=theme.RADIUS_SM)
        self.review_banner.grid_columnconfigure(0, weight=1)
        self.banner_text = label(self.review_banner, "", "bold", theme.ACCENT)
        self.banner_text.grid(row=0, column=0, sticky="w", padx=14, pady=10)
        primary_button(self.review_banner, "Voir la liste", lambda: self.app.show("review"),
                       height=30, width=110).grid(row=0, column=1, padx=10)

        # --- Activité récente ------------------------------------------------
        activity = Panel(self)
        activity.grid(row=3, column=0, sticky="nsew", padx=theme.PAD, pady=(0, theme.PAD))
        activity.grid_columnconfigure(0, weight=1)
        activity.grid_rowconfigure(1, weight=1)
        label(activity, "Activité récente", "heading").grid(row=0, column=0, sticky="w", padx=20, pady=(16, 6))
        self.feed = ctk.CTkScrollableFrame(activity, fg_color="transparent")
        self.feed.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.feed.grid_columnconfigure(1, weight=1)
        self.empty = label(self.feed, "Aucune activité pour l'instant. Activez la surveillance ou "
                                      "analysez le dossier pour commencer.", "body", theme.MUTED)
        self._rows: list[ctk.CTkFrame] = []

        for item in reversed(list(self.app.engine.recent)[:MAX_ROWS]):
            self.add_activity(item)
        self.refresh()

    # ------------------------------------------------------------------ mise à jour

    def refresh(self) -> None:
        engine = self.app.engine
        settings = self.app.settings
        mode = "rangés automatiquement" if settings.mode == MODE_AUTO else "soumis à votre validation"
        self.source_label.configure(
            text=f"Les nouveaux fichiers de {contract_path(settings.source_path)} sont {mode}.")
        pending = engine.pending_count()
        self.figures["sorted"].configure(text=str(engine.stats.sorted_today))
        self.figures["pending"].configure(text=str(pending))
        self.figures["duplicates"].configure(text=str(engine.stats.duplicates_today))
        self.figures["errors"].configure(text=str(engine.stats.errors))
        if pending:
            plural = "s attendent" if pending > 1 else " attend"
            self.banner_text.configure(text=f"{pending} fichier{plural} votre validation.")
            self.review_banner.grid(row=1, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 16))
        else:
            self.review_banner.grid_forget()
        if not self._rows:
            self.empty.grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=12)

    def add_activity(self, item: Activity) -> None:
        self.empty.grid_forget()
        row = ctk.CTkFrame(self.feed, fg_color="transparent")
        row.grid_columnconfigure(2, weight=1)
        color = self.app.category_color(item.category) if item.category else theme.LEVEL_COLORS.get(item.level, theme.MUTED)
        Tab(row, color, height=22).grid(row=0, column=0, padx=(4, 10), pady=5)
        label(row, datetime.fromtimestamp(item.timestamp).strftime("%H:%M"), "small", theme.FAINT, width=40).grid(
            row=0, column=1, sticky="w")
        text_color = theme.DANGER if item.level == "error" else theme.TEXT
        label(row, item.message, "body", text_color).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        if item.path and item.level in ("success", "warning", "info") and Path(item.path).exists():
            ghost_button(row, "Afficher", lambda p=item.path: self._reveal(p)).grid(row=0, column=3, padx=6)

        self._rows.insert(0, row)
        for index, widget in enumerate(self._rows):
            widget.grid(row=index, column=0, columnspan=3, sticky="ew")
        while len(self._rows) > MAX_ROWS:
            self._rows.pop().destroy()

    def _reveal(self, path: str) -> None:
        target = Path(path)
        if target.exists():
            open_in_file_manager(target)
        else:
            self.app.toast("Cet élément a été déplacé depuis.", "warning")

    def _open_source(self) -> None:
        source = self.app.settings.source_path
        if source.exists():
            open_in_file_manager(source)
        else:
            self.app.toast(f"Dossier introuvable : {source}", "error")

# GROGNON
