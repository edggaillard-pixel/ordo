"""Écran « À valider » : l'utilisateur relit, corrige ou refuse chaque proposition.

Flux : les propositions arrivent cochées. On décoche ou on clique « Ignorer »
pour celles qu'on refuse, « Modifier » pour changer le nom, la catégorie ou
le dossier, puis « Valider la sélection » range tout d'un coup. Le lot validé
reste annulable depuis l'Historique.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from app.core.models import ActionKind, PlannedAction
from app.gui import theme
from app.gui.dialogs import EditActionDialog
from app.gui.widgets import Panel, Pill, Tab, ghost_button, label, primary_button, secondary_button
from app.system.paths import contract_path

if TYPE_CHECKING:
    from app.gui.app_window import AppWindow

MAX_VISIBLE = 300  # au-delà, Tk ralentit ; le reste s'affiche après validation


def _signature(action: PlannedAction) -> tuple:
    return (action.new_name, str(action.target_dir), action.category, action.kind,
            action.error, action.user_edited, str(action.extract_to))


class ReviewView(ctk.CTkFrame):
    def __init__(self, master, app: "AppWindow") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._rows: dict[str, tuple[ctk.CTkFrame, tuple]] = {}
        self._checks: dict[str, ctk.BooleanVar] = {}
        self._actions: dict[str, PlannedAction] = {}

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD, 4))
        head.grid_columnconfigure(0, weight=1)
        label(head, "À valider", "title").grid(row=0, column=0, sticky="w")
        self.reject_btn = secondary_button(head, "Ignorer la sélection", self._reject_selected)
        self.reject_btn.grid(row=0, column=1, padx=(0, 8))
        self.approve_btn = primary_button(head, "Valider la sélection", self._approve_selected, width=210)
        self.approve_btn.grid(row=0, column=2)

        label(self, "Relisez les propositions, modifiez celles qui ne vous conviennent pas, puis validez. "
                    "Un lot validé reste annulable depuis l'Historique.",
              "body", theme.MUTED, wraplength=760).grid(row=1, column=0, sticky="w", padx=theme.PAD)

        panel = Panel(self)
        panel.grid(row=2, column=0, sticky="nsew", padx=theme.PAD, pady=(16, theme.PAD))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        toolbar.grid_columnconfigure(1, weight=1)
        self.all_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(toolbar, text="Tout sélectionner", variable=self.all_var, command=self._toggle_all,
                        font=theme.body(), text_color=theme.TEXT, fg_color=theme.ACCENT,
                        hover_color=theme.ACCENT_HOVER, border_color=theme.FAINT, checkbox_width=18,
                        checkbox_height=18, corner_radius=4).grid(row=0, column=0, sticky="w")
        self.count_label = label(toolbar, "", "small", theme.MUTED)
        self.count_label.grid(row=0, column=1, sticky="e")
        ctk.CTkFrame(panel, height=1, fg_color=theme.LINE).grid(row=0, column=0, sticky="sew", padx=1)

        self.list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.list.grid(row=1, column=0, sticky="nsew", padx=4, pady=(4, 8))
        self.list.grid_columnconfigure(0, weight=1)

        self.empty = ctk.CTkFrame(self.list, fg_color="transparent")
        label(self.empty, "Rien à valider", "heading", theme.TEXT, anchor="center").pack(pady=(70, 6))
        label(self.empty, "Les nouveaux téléchargements apparaîtront ici dès qu'ils seront terminés.\n"
                          "Pour traiter les fichiers déjà présents, utilisez « Analyser le dossier ».",
              "body", theme.MUTED, anchor="center", justify="center").pack()
        secondary_button(self.empty, "Analyser le dossier", self.app.engine.scan_now, icon="scan").pack(pady=18)

        self.refresh()

    # --------------------------------------------------------------- rendu

    def refresh(self) -> None:
        pending = self.app.engine.pending()
        current = {a.id: a for a in pending[:MAX_VISIBLE]}
        self._actions = current

        for action_id in list(self._rows):
            if action_id not in current:
                self._rows.pop(action_id)[0].destroy()
                self._checks.pop(action_id, None)

        for index, action in enumerate(current.values()):
            sig = _signature(action)
            existing = self._rows.get(action.id)
            if existing is None or existing[1] != sig:
                if existing is not None:
                    existing[0].destroy()
                row = self._build_row(action)
                self._rows[action.id] = (row, sig)
            self._rows[action.id][0].grid(row=index, column=0, sticky="ew")

        if current:
            self.empty.grid_forget()
        else:
            self.empty.grid(row=0, column=0, sticky="nsew")
        self._update_counts(len(pending))

    def _build_row(self, action: PlannedAction) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.list, fg_color="transparent", corner_radius=theme.RADIUS_SM)
        row.grid_columnconfigure(2, weight=1)

        var = self._checks.setdefault(action.id, ctk.BooleanVar(value=True))
        ctk.CTkCheckBox(row, text="", variable=var, width=24, command=self._update_counts,
                        fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, border_color=theme.FAINT,
                        checkbox_width=18, checkbox_height=18, corner_radius=4).grid(
            row=0, column=0, rowspan=3, padx=(12, 6))
        color = self.app.category_color(action.category)
        Tab(row, color, height=46).grid(row=0, column=1, rowspan=3, padx=(0, 12), pady=10)

        top = ctk.CTkFrame(row, fg_color="transparent")
        top.grid(row=0, column=2, sticky="ew", pady=(10, 0))
        label(top, action.new_name, "bold").pack(side="left")
        if action.kind is ActionKind.DUPLICATE:
            Pill(top, "doublon", theme.WARNING).pack(side="left", padx=(8, 0))
        if action.user_edited:
            Pill(top, "modifié", theme.ACCENT, theme.ACCENT_SOFT).pack(side="left", padx=(8, 0))
        if action.rule:
            Pill(top, f"règle {action.rule}").pack(side="left", padx=(8, 0))
        if action.extract_to is not None and action.kind is ActionKind.MOVE:
            Pill(top, "sera décompressée").pack(side="left", padx=(8, 0))

        if action.kind is ActionKind.DUPLICATE and action.duplicate_of is not None:
            origin = f"{action.original_name} est identique à {contract_path(action.duplicate_of)}"
        elif action.renamed:
            origin = f"Renommé depuis {action.original_name}"
        else:
            origin = "Nom conservé"
        label(row, origin, "small", theme.MUTED).grid(row=1, column=2, sticky="ew")

        destination = f"{action.category}  ›  {contract_path(action.target_dir)}"
        if action.error:
            destination = f"Échec : {action.error}"
        label(row, destination, "small", theme.DANGER if action.error else theme.FAINT).grid(
            row=2, column=2, sticky="ew", pady=(0, 10))

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=3, rowspan=3, padx=(8, 12))
        ghost_button(actions, "Modifier", lambda a=action.id: self._edit(a), color=theme.TEXT,
                     icon="edit").pack(side="left")
        ghost_button(actions, "Ignorer", lambda a=action.id: self.app.engine.reject([a]),
                     icon="close").pack(side="left", padx=(4, 0))

        ctk.CTkFrame(row, height=1, fg_color=theme.LINE).grid(row=3, column=0, columnspan=4, sticky="ew", padx=12)
        return row

    # ------------------------------------------------------------- actions

    def _selected(self) -> list[str]:
        return [i for i, v in self._checks.items() if v.get() and i in self._actions]

    def _update_counts(self, total: int | None = None) -> None:
        total = self.app.engine.pending_count() if total is None else total
        selected = len(self._selected())
        self.approve_btn.configure(
            text=f"Valider la sélection ({selected})" if selected else "Valider la sélection",
            state="normal" if selected else "disabled",
        )
        self.reject_btn.configure(state="normal" if selected else "disabled")
        hidden = max(0, total - len(self._actions))
        text = f"{selected} sur {total} sélectionné{'s' if selected > 1 else ''}" if total else ""
        if hidden:
            text += f", {hidden} autres s'afficheront ensuite"
        self.count_label.configure(text=text)
        self.all_var.set(bool(self._actions) and selected == len(self._actions))

    def _toggle_all(self) -> None:
        value = self.all_var.get()
        for var in self._checks.values():
            var.set(value)
        self._update_counts()

    def _approve_selected(self) -> None:
        ids = self._selected()
        if ids:
            self.app.engine.approve(ids)
            self.app.toast(f"Rangement de {len(ids)} élément{'s' if len(ids) > 1 else ''} en cours…")

    def _reject_selected(self) -> None:
        ids = self._selected()
        if ids:
            self.app.engine.reject(ids)

    def _edit(self, action_id: str) -> None:
        action = self._actions.get(action_id)
        if action is None:
            return
        EditActionDialog(self, self.app, action)

# GROGNON
