"""Fenêtre « Modifier la proposition »."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.core.classifier import DUPLICATES_CATEGORY, FOLDERS_CATEGORY
from app.core.models import PlannedAction
from app.core.renamer import split_name
from app.gui import theme
from app.gui.widgets import PathField, center_on_parent, entry, label, option_menu, primary_button, secondary_button
from app.system.paths import contract_path, expand_path

if TYPE_CHECKING:
    from app.gui.app_window import AppWindow

_FORBIDDEN = set('<>:"/\\|?*')


class EditActionDialog(ctk.CTkToplevel):
    def __init__(self, master, app: "AppWindow", action: PlannedAction) -> None:
        super().__init__(master)
        self.app = app
        self.action = action
        self.title("Modifier la proposition")
        self.configure(fg_color=theme.PANEL)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grid_columnconfigure(0, weight=1)

        label(self, "Modifier la proposition", "heading").grid(row=0, column=0, sticky="w", padx=24, pady=(22, 2))
        label(self, f"Fichier d'origine : {action.original_name}", "small", theme.MUTED).grid(
            row=1, column=0, sticky="w", padx=24)

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, sticky="ew", padx=24, pady=(18, 0))
        form.grid_columnconfigure(0, weight=1)

        # Nom (l'extension est verrouillée pour éviter de rendre le fichier illisible).
        stem, self.ext = split_name(action.new_name, action.is_dir)
        label(form, "Nouveau nom", "bold").grid(row=0, column=0, sticky="w")
        name_row = ctk.CTkFrame(form, fg_color="transparent")
        name_row.grid(row=1, column=0, sticky="ew", pady=(4, 14))
        name_row.grid_columnconfigure(0, weight=1)
        self.name_var = ctk.StringVar(value=stem)
        self.name_entry = entry(name_row, textvariable=self.name_var, width=420)
        self.name_entry.grid(row=0, column=0, sticky="ew")
        if self.ext:
            label(name_row, self.ext, "body", theme.MUTED).grid(row=0, column=1, padx=(8, 0))
        secondary_button(name_row, "Nom d'origine", self._restore_original, height=34).grid(
            row=0, column=2, padx=(8, 0))

        # Catégorie.
        label(form, "Catégorie", "bold").grid(row=2, column=0, sticky="w")
        if action.is_dir:
            choices = [FOLDERS_CATEGORY]
        else:
            choices = [c.name for c in app.settings.categories] + [DUPLICATES_CATEGORY]
        self.category_var = ctk.StringVar(value=action.category or choices[0])
        option_menu(form, choices, command=self._category_changed, variable=self.category_var,
                    width=260).grid(row=3, column=0, sticky="w", pady=(4, 14))

        # Dossier de destination.
        label(form, "Dossier de destination", "bold").grid(row=4, column=0, sticky="w")
        self.path_field = PathField(form, contract_path(action.target_dir), lambda _v: self._update_preview())
        self.path_field.grid(row=5, column=0, sticky="ew", pady=(4, 14))

        self.preview = label(form, "", "small", theme.MUTED, wraplength=560)
        self.preview.grid(row=6, column=0, sticky="w")
        self.error = label(form, "", "small", theme.DANGER)
        self.error.grid(row=7, column=0, sticky="w", pady=(4, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=24, pady=(16, 22))
        primary_button(buttons, "Enregistrer", self._save, width=130).pack(side="right")
        secondary_button(buttons, "Annuler", self.destroy).pack(side="right", padx=(0, 8))

        self.name_var.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._save())
        center_on_parent(self, master.winfo_toplevel())
        self.after(60, self._focus)

    def _focus(self) -> None:
        try:
            self.grab_set()
            self.name_entry.focus_set()
            self.name_entry.select_range(0, "end")
        except Exception:  # noqa: BLE001
            pass

    def _restore_original(self) -> None:
        self.name_var.set(split_name(self.action.original_name, self.action.is_dir)[0])

    def _category_changed(self, category: str) -> None:
        target = self.app.engine.preview_category(self.action.id, category)
        if target is not None:
            self.path_field.var.set(str(target))

    def _final_name(self) -> str:
        return self.name_var.get().strip() + self.ext

    def _update_preview(self) -> None:
        target = self.path_field.var.get().strip()
        path = expand_path(target) / self._final_name() if target else None
        self.preview.configure(text=f"Sera rangé ici : {contract_path(path)}" if path else "")
        self.error.configure(text=self._problem() or "")

    def _problem(self) -> str | None:
        stem = self.name_var.get().strip()
        if not stem:
            return "Le nom ne peut pas être vide."
        if any(ch in _FORBIDDEN for ch in stem):
            return "Ces caractères ne sont pas autorisés : < > : \" / \\ | ? *"
        if not self.path_field.var.get().strip():
            return "Choisissez un dossier de destination."
        destination = expand_path(self.path_field.var.get()) / self._final_name()
        if destination.exists():
            return "Un élément porte déjà ce nom : un suffixe horodaté sera ajouté."
        return None

    def _save(self) -> None:
        problem = self._problem()
        if problem and "suffixe" not in problem:
            self.error.configure(text=problem)
            return
        category = self.category_var.get()
        target = expand_path(self.path_field.var.get())
        updated = self.app.engine.update_pending(
            self.action.id,
            new_name=self._final_name(),
            category=category if category != self.action.category else None,
            target_dir=Path(target),
        )
        if updated is None:
            self.app.toast("Ce fichier n'est plus en attente.", "warning")
        self.destroy()

# GROGNON
