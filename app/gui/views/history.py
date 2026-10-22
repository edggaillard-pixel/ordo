"""Historique : les lots de rangement, chacun annulable."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.core.models import Batch
from app.fs.file_ops import open_in_file_manager
from app.gui import theme
from app.gui.widgets import ConfirmDialog, Panel, Pill, Tab, ghost_button, label, secondary_button
from app.system.paths import contract_path, log_dir

if TYPE_CHECKING:
    from app.gui.app_window import AppWindow

MAX_BATCHES = 60
ENTRIES_SHOWN = 6


def _when(timestamp: float) -> str:
    moment = datetime.fromtimestamp(timestamp)
    today = datetime.now().date()
    if moment.date() == today:
        day = "Aujourd'hui"
    elif moment.date() == today - timedelta(days=1):
        day = "Hier"
    else:
        day = moment.strftime("%d/%m/%Y")
    return f"{day} à {moment:%H:%M}"


class HistoryView(ctk.CTkFrame):
    def __init__(self, master, app: "AppWindow") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD, 4))
        head.grid_columnconfigure(0, weight=1)
        label(head, "Historique", "title").grid(row=0, column=0, sticky="w")
        secondary_button(head, "Journal technique", lambda: open_in_file_manager(log_dir()), icon="folder").grid(
            row=0, column=1)
        label(self, "Chaque validation forme un lot. Annuler un lot remet ses fichiers dans le dossier "
                    "surveillé ; ils ne seront pas rangés de nouveau tant qu'ils ne changent pas.",
              "body", theme.MUTED, wraplength=760).grid(row=1, column=0, sticky="w", padx=theme.PAD)

        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.grid(row=2, column=0, sticky="nsew", padx=theme.PAD - 6, pady=(14, theme.PAD))
        self.list.grid_columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        batches = self.app.engine.journal.batches(MAX_BATCHES)
        if not batches:
            label(self.list, "Aucun rangement pour l'instant.", "heading", anchor="center").pack(pady=(80, 6))
            label(self.list, "Les fichiers rangés apparaîtront ici, regroupés par validation.",
                  "body", theme.MUTED, anchor="center").pack()
            return
        for index, batch in enumerate(batches):
            self._batch_panel(batch).grid(row=index, column=0, sticky="ew", padx=6, pady=(0, theme.GAP))

    def _batch_panel(self, batch: Batch) -> ctk.CTkFrame:
        panel = Panel(self.list)
        panel.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 6))
        top.grid_columnconfigure(1, weight=1)
        label(top, _when(batch.timestamp), "bold").grid(row=0, column=0, sticky="w")
        count = f"{batch.size} élément{'s' if batch.size > 1 else ''}"
        label(top, count, "small", theme.MUTED).grid(row=0, column=1, sticky="w", padx=10)
        if batch.undone:
            Pill(top, "annulé").grid(row=0, column=2)
        else:
            ghost_button(top, "Annuler ce lot", lambda b=batch: self._undo(b), color=theme.DANGER,
                         icon="undo").grid(row=0, column=2)

        for i, entry in enumerate(batch.entries[:ENTRIES_SHOWN]):
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.grid(row=i + 1, column=0, sticky="ew", padx=18)
            row.grid_columnconfigure(1, weight=1)
            Tab(row, self.app.category_color(entry.category), height=18).grid(row=0, column=0, padx=(0, 10), pady=3)
            text = f"{entry.source_path.name}  ›  {contract_path(entry.destination_path)}"
            color = theme.FAINT if entry.undone else theme.TEXT
            label(row, text, "small", color).grid(row=0, column=1, sticky="ew")
            if not entry.undone:
                ghost_button(row, "Afficher", lambda p=entry.destination: self._reveal(p), height=24).grid(
                    row=0, column=2)
        extra = batch.size - ENTRIES_SHOWN
        if extra > 0:
            label(panel, f"et {extra} autre{'s' if extra > 1 else ''}", "small", theme.MUTED).grid(
                row=ENTRIES_SHOWN + 1, column=0, sticky="w", padx=32)
        ctk.CTkFrame(panel, height=8, fg_color="transparent").grid(row=ENTRIES_SHOWN + 2, column=0)
        return panel

    def _undo(self, batch: Batch) -> None:
        plural = "s" if batch.size > 1 else ""
        if ConfirmDialog.ask(
            self, "Annuler ce lot ?",
            f"{batch.size} élément{plural} retourne{'nt' if plural else ''} dans "
            f"{contract_path(self.app.settings.source_path)} avec {'leur' if plural else 'son'} nom d'origine. "
            "Les dossiers créés par décompression vont à la corbeille.",
            "Annuler le lot", danger=True,
        ):
            self.app.engine.undo(batch.id)

    def _reveal(self, path: str) -> None:
        target = Path(path)
        if target.exists():
            open_in_file_manager(target)
        else:
            self.app.toast("Cet élément n'est plus à cet emplacement.", "warning")
