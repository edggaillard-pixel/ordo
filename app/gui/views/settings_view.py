"""Réglages : édition d'un brouillon, validé puis appliqué d'un coup.

Rien n'est pris en compte avant « Enregistrer » : on peut explorer les
options sans risque, et « Rétablir » revient à l'état enregistré.
"""

from __future__ import annotations

from collections.abc import Callable
from tkinter import colorchooser
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.config import defaults
from app.config.settings import MODE_AUTO, MODE_REVIEW, Category, NameRule, Settings, validate
from app.core import renamer
from app.fs.file_ops import open_in_file_manager
from app.gui import theme
from app.gui.widgets import (
    ConfirmDialog, PathField, entry, ghost_button, label, option_menu, primary_button, secondary_button, switch,
)
from app.system.paths import config_dir, log_dir

if TYPE_CHECKING:
    from app.gui.app_window import AppWindow

DATE_FORMATS = {
    "2026-10-22": "%Y-%m-%d",
    "20261022": "%Y%m%d",
    "2026-10": "%Y-%m",
    "22-10-2026": "%d-%m-%Y",
}
ORGANIZE_BY_LABEL = {v: k for k, v in defaults.ORGANIZE_LABELS.items()}
PALETTE = ["#4F7DF3", "#2FB37A", "#D9668F", "#9B6CF0", "#E5A23A", "#37B6C9", "#8B93A1", "#C9A227"]


def _split_list(text: str) -> list[str]:
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, app: "AppWindow") -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.draft: Settings = app.settings.copy()
        self.dirty = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD, 0))
        head.grid_columnconfigure(1, weight=1)
        label(head, "Réglages", "title").grid(row=0, column=0, sticky="w")
        self.dirty_label = label(head, "", "small", theme.WARNING)
        self.dirty_label.grid(row=0, column=1, sticky="w", padx=14)
        self.revert_btn = secondary_button(head, "Rétablir", self._revert)
        self.revert_btn.grid(row=0, column=2, padx=(0, 8))
        self.save_btn = primary_button(head, "Enregistrer", self._save, width=130)
        self.save_btn.grid(row=0, column=3)

        self.errors = ctk.CTkFrame(self, fg_color=theme.RAISED, corner_radius=theme.RADIUS_SM,
                                   border_width=1, border_color=theme.DANGER)
        self.errors_text = label(self.errors, "", "body", theme.DANGER, wraplength=780)
        self.errors_text.pack(anchor="w", padx=14, pady=10)

        self.tabs = ctk.CTkTabview(
            self, fg_color=theme.PANEL, border_width=1, border_color=theme.LINE, corner_radius=theme.RADIUS,
            segmented_button_fg_color=theme.RAISED, segmented_button_selected_color=theme.ACCENT,
            segmented_button_selected_hover_color=theme.ACCENT_HOVER,
            segmented_button_unselected_color=theme.RAISED, segmented_button_unselected_hover_color=theme.LINE,
            text_color=theme.TEXT, anchor="w",
        )
        self.tabs._segmented_button.configure(font=theme.body())
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=theme.PAD, pady=(10, theme.PAD))
        self._build_tabs()
        self._set_dirty(False)

    # ================================================================ structure

    def _build_tabs(self) -> None:
        builders = [
            ("Général", self._general),
            ("Catégories", self._categories),
            ("Règles par nom", self._rules),
            ("Renommage", self._rename),
            ("Avancé", self._advanced),
        ]
        self._bodies: dict[str, ctk.CTkScrollableFrame] = {}
        for name, builder in builders:
            tab = self.tabs.add(name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)
            body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
            body.grid(row=0, column=0, sticky="nsew")
            body.grid_columnconfigure(0, weight=1)
            self._bodies[name] = body
            builder(body)

    def _rebuild(self, tab: str, builder: Callable) -> None:
        body = self._bodies[tab]
        for child in body.winfo_children():
            child.destroy()
        builder(body)

    def _setting(self, parent, row: int, title: str, help_text: str, control_factory: Callable,
                 stacked: bool = False) -> int:
        """Ligne de réglage : intitulé et explication à gauche, contrôle à droite (ou dessous)."""
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=row, column=0, sticky="ew", padx=12, pady=(14, 0))
        box.grid_columnconfigure(0, weight=1)
        label(box, title, "bold").grid(row=0, column=0, sticky="w")
        if help_text:
            label(box, help_text, "small", theme.MUTED, wraplength=520).grid(row=1, column=0, sticky="w", pady=(2, 0))
        control = control_factory(box)
        if stacked:
            control.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        else:
            control.grid(row=0, column=1, rowspan=2, sticky="e", padx=(20, 0))
        ctk.CTkFrame(parent, height=1, fg_color=theme.LINE).grid(row=row + 1, column=0, sticky="ew", padx=12,
                                                               pady=(14, 0))
        return row + 2

    def _switch(self, getter: Callable[[], bool], setter: Callable[[bool], None]) -> Callable:
        def factory(parent):
            sw = switch(parent, command=lambda: (setter(bool(sw.get())), self._changed()))
            if getter():
                sw.select()
            return sw
        return factory

    def _segmented(self, values: list[str], current: str, setter: Callable[[str], None]) -> Callable:
        def factory(parent):
            seg = ctk.CTkSegmentedButton(
                parent, values=values, font=theme.body(), fg_color=theme.RAISED,
                selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
                unselected_color=theme.RAISED, unselected_hover_color=theme.LINE, text_color=theme.TEXT,
                command=lambda v: (setter(v), self._changed()),
            )
            seg.set(current)
            return seg
        return factory

    # ================================================================ Général

    def _general(self, body) -> None:
        d = self.draft
        r = self._setting(body, 0, "Dossier surveillé",
                          "Les nouveaux fichiers qui arrivent ici sont triés. En général : Téléchargements.",
                          lambda p: PathField(p, d.source_dir, lambda v: self._set(d, "source_dir", v)),
                          stacked=True)
        modes = {"Validation manuelle": MODE_REVIEW, "Automatique": MODE_AUTO}
        r = self._setting(body, r, "Mode de fonctionnement",
                          "Validation manuelle : chaque fichier attend votre accord dans « À valider ». "
                          "Automatique : rangement immédiat, annulable depuis l'Historique.",
                          self._segmented(list(modes), next(k for k, v in modes.items() if v == d.mode),
                                          lambda v: setattr(d, "mode", modes[v])))

        def stability(parent):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            value = label(frame, f"{d.stability_seconds:g} s", "bold", width=46, anchor="e")

            def moved(v: float) -> None:
                d.stability_seconds = round(float(v))
                value.configure(text=f"{d.stability_seconds:g} s")
                self._changed()

            slider = ctk.CTkSlider(frame, from_=1, to=30, number_of_steps=29, width=200, command=moved,
                                   progress_color=theme.ACCENT, button_color=theme.ACCENT,
                                   button_hover_color=theme.ACCENT_HOVER, fg_color=theme.LINE)
            slider.set(min(30, max(1, d.stability_seconds)))
            slider.pack(side="left")
            value.pack(side="left", padx=(8, 0))
            return frame

        r = self._setting(body, r, "Délai avant traitement",
                          "Un fichier est traité quand sa taille n'a plus changé depuis ce délai. "
                          "Augmentez-le si vos téléchargements passent par un réseau lent.", stability)
        r = self._setting(body, r, "Notifications", "Prévient quand des fichiers attendent votre validation, "
                          "quand un rangement est fait ou en cas d'échec.",
                          self._switch(lambda: d.notifications, lambda v: setattr(d, "notifications", v)))
        r = self._setting(body, r, "Surveiller dès l'ouverture",
                          "Reprend la surveillance automatiquement au lancement de l'application.",
                          self._switch(lambda: d.start_watching_on_launch,
                                       lambda v: setattr(d, "start_watching_on_launch", v)))
        r = self._setting(body, r, "Lancer avec l'ordinateur",
                          "Ordo démarre en arrière-plan à l'ouverture de votre session.",
                          self._switch(lambda: d.start_with_system, lambda v: setattr(d, "start_with_system", v)))
        if self.app.tray_available:
            help_close = "La fermeture de la fenêtre laisse Ordo tourner dans la zone de notification."
        else:
            help_close = "La fermeture de la fenêtre la réduit dans le Dock au lieu de quitter."
        r = self._setting(body, r, "Continuer en arrière-plan", help_close,
                          self._switch(lambda: d.close_to_tray, lambda v: setattr(d, "close_to_tray", v)))
        themes = {"Sombre": "dark", "Clair": "light", "Système": "system"}
        self._setting(body, r, "Apparence", "",
                      self._segmented(list(themes), next(k for k, v in themes.items() if v == d.appearance),
                                      lambda v: setattr(d, "appearance", themes[v])))

    # ================================================================ Catégories

    def _categories(self, body) -> None:
        label(body, "Chaque extension mène à une catégorie, et chaque catégorie à un dossier. "
                    "Les fichiers dont l'extension n'est listée nulle part restent dans le dossier surveillé.",
              "body", theme.MUTED, wraplength=760).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        row = 1
        for cat in self.draft.categories:
            self._category_block(body, cat).grid(row=row, column=0, sticky="ew", padx=12, pady=(12, 0))
            row += 1
        secondary_button(body, "Ajouter une catégorie", self._add_category).grid(
            row=row, column=0, sticky="w", padx=12, pady=16)

    def _category_block(self, body, cat: Category) -> ctk.CTkFrame:
        block = ctk.CTkFrame(body, fg_color=theme.RAISED, corner_radius=theme.RADIUS_SM,
                             border_width=1, border_color=theme.LINE)
        block.grid_columnconfigure(2, weight=1)

        swatch = ctk.CTkButton(block, text="", width=22, height=22, corner_radius=11, fg_color=cat.color,
                               hover_color=cat.color, border_width=0)
        swatch.configure(command=lambda: self._pick_color(cat, swatch))
        swatch.grid(row=0, column=0, padx=(14, 10), pady=(14, 6))

        name_var = ctk.StringVar(value=cat.name)

        def renamed(*_):
            old, new = cat.name, name_var.get().strip()
            for rule in self.draft.name_rules:  # les règles suivent le renommage
                if rule.category == old:
                    rule.category = new
            cat.name = new
            self._changed()

        name_var.trace_add("write", renamed)
        entry(block, textvariable=name_var, width=170, font=theme.body_bold()).grid(
            row=0, column=1, sticky="w", pady=(14, 6))

        organize = option_menu(block, list(defaults.ORGANIZE_LABELS.values()), width=180,
                               command=lambda v: (setattr(cat, "organize", ORGANIZE_BY_LABEL[v]), self._changed()))
        organize.set(defaults.ORGANIZE_LABELS.get(cat.organize, defaults.ORGANIZE_LABELS[defaults.ORGANIZE_NONE]))
        organize.grid(row=0, column=3, sticky="e", padx=(8, 4), pady=(14, 6))
        ghost_button(block, "Supprimer", lambda: self._remove_category(cat), color=theme.DANGER).grid(
            row=0, column=4, padx=(0, 10), pady=(14, 6))

        label(block, "Extensions", "small", theme.MUTED).grid(row=1, column=1, sticky="w")
        ext_var = ctk.StringVar(value=", ".join(cat.normalized_extensions()))
        ext_var.trace_add("write", lambda *_: (setattr(cat, "extensions", _split_list(ext_var.get())), self._changed()))
        entry(block, textvariable=ext_var).grid(row=2, column=1, columnspan=4, sticky="ew", padx=(0, 14))

        label(block, "Dossier cible", "small", theme.MUTED).grid(row=3, column=1, sticky="w", pady=(8, 0))
        PathField(block, cat.target, lambda v: self._set(cat, "target", v)).grid(
            row=4, column=1, columnspan=4, sticky="ew", padx=(0, 14), pady=(0, 14))
        return block

    def _pick_color(self, cat: Category, swatch: ctk.CTkButton) -> None:
        _, color = colorchooser.askcolor(color=cat.color, parent=self.winfo_toplevel(), title="Couleur de l'onglet")
        if color:
            cat.color = color
            swatch.configure(fg_color=color, hover_color=color)
            self._changed()

    def _add_category(self) -> None:
        used = {c.color for c in self.draft.categories}
        color = next((c for c in PALETTE if c not in used), PALETTE[len(self.draft.categories) % len(PALETTE)])
        name = "Nouvelle catégorie"
        n = 2
        while self.draft.category(name):
            name = f"Nouvelle catégorie {n}"
            n += 1
        self.draft.categories.append(Category(name=name, extensions=[], target="{documents}/Ordo/" + name,
                                              color=color))
        self._rebuild("Catégories", self._categories)
        self._changed()

    def _remove_category(self, cat: Category) -> None:
        used_by = [r.name for r in self.draft.name_rules if r.category == cat.name]
        message = f"Les fichiers .{', .'.join(cat.normalized_extensions()[:5]) or '…'} ne seront plus rangés."
        if used_by:
            message += f" Les règles qui l'utilisent seront aussi supprimées : {', '.join(used_by)}."
        if not ConfirmDialog.ask(self, f"Supprimer « {cat.name} » ?", message, "Supprimer", danger=True):
            return
        self.draft.categories.remove(cat)
        self.draft.name_rules = [r for r in self.draft.name_rules if r.category != cat.name]
        self._rebuild("Catégories", self._categories)
        self._rebuild("Règles par nom", self._rules)
        self._changed()

    # ================================================================ Règles

    def _rules(self, body) -> None:
        label(body, "Ces règles passent avant les extensions, dans l'ordre de la liste : la première qui "
                    "correspond au nom du fichier l'emporte. Motifs : * remplace n'importe quels caractères, "
                    "plusieurs motifs se séparent par « ; », et « re: » introduit une expression régulière. "
                    "Majuscules et minuscules sont confondues.",
              "body", theme.MUTED, wraplength=760).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        row = 1
        for index, rule in enumerate(self.draft.name_rules):
            self._rule_block(body, rule, index).grid(row=row, column=0, sticky="ew", padx=12, pady=(12, 0))
            row += 1
        if not self.draft.name_rules:
            label(body, "Aucune règle : seules les extensions comptent.", "body", theme.FAINT).grid(
                row=row, column=0, sticky="w", padx=12, pady=12)
            row += 1
        secondary_button(body, "Ajouter une règle", self._add_rule).grid(row=row, column=0, sticky="w",
                                                                        padx=12, pady=16)

    def _rule_block(self, body, rule: NameRule, index: int) -> ctk.CTkFrame:
        block = ctk.CTkFrame(body, fg_color=theme.RAISED, corner_radius=theme.RADIUS_SM,
                             border_width=1, border_color=theme.LINE)
        block.grid_columnconfigure(1, weight=1)
        block.grid_columnconfigure(2, weight=1)

        top = ctk.CTkFrame(block, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=3, sticky="ew", padx=14, pady=(12, 4))
        top.grid_columnconfigure(1, weight=1)
        sw = switch(top, command=lambda: (setattr(rule, "enabled", bool(sw.get())), self._changed()))
        if rule.enabled:
            sw.select()
        sw.grid(row=0, column=0)
        name_var = ctk.StringVar(value=rule.name)
        name_var.trace_add("write", lambda *_: self._set(rule, "name", name_var.get()))
        entry(top, textvariable=name_var, width=220, font=theme.body_bold(),
              placeholder_text="Nom de la règle").grid(row=0, column=1, sticky="w")
        ghost_button(top, "Monter", lambda: self._move_rule(index, -1),
                     state="normal" if index else "disabled").grid(row=0, column=2)
        ghost_button(top, "Descendre", lambda: self._move_rule(index, 1),
                     state="normal" if index < len(self.draft.name_rules) - 1 else "disabled").grid(row=0, column=3)
        ghost_button(top, "Supprimer", lambda: self._remove_rule(rule), color=theme.DANGER).grid(row=0, column=4)

        label(block, "Le nom correspond à", "small", theme.MUTED).grid(row=1, column=0, columnspan=3, sticky="w",
                                                                      padx=14)
        pat_var = ctk.StringVar(value=rule.patterns)
        pat_var.trace_add("write", lambda *_: self._set(rule, "patterns", pat_var.get()))
        entry(block, textvariable=pat_var, placeholder_text="*facture*;*invoice*").grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=14)

        label(block, "Catégorie", "small", theme.MUTED).grid(row=3, column=0, sticky="w", padx=14, pady=(8, 0))
        label(block, "Sous-dossier (facultatif)", "small", theme.MUTED).grid(row=3, column=1, columnspan=2,
                                                                            sticky="w", pady=(8, 0))
        names = [c.name for c in self.draft.categories] or ["—"]
        cat_menu = option_menu(block, names, width=200,
                               command=lambda v: (setattr(rule, "category", v), self._changed()))
        cat_menu.set(rule.category if rule.category in names else names[0])
        cat_menu.grid(row=4, column=0, sticky="w", padx=14, pady=(0, 14))
        sub_var = ctk.StringVar(value=rule.subfolder)
        sub_var.trace_add("write", lambda *_: self._set(rule, "subfolder", sub_var.get()))
        entry(block, textvariable=sub_var, placeholder_text="Factures").grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(0, 14))
        return block

    def _add_rule(self) -> None:
        first = self.draft.categories[0].name if self.draft.categories else ""
        self.draft.name_rules.append(NameRule(name="Nouvelle règle", patterns="", category=first))
        self._rebuild("Règles par nom", self._rules)
        self._changed()

    def _remove_rule(self, rule: NameRule) -> None:
        self.draft.name_rules.remove(rule)
        self._rebuild("Règles par nom", self._rules)
        self._changed()

    def _move_rule(self, index: int, delta: int) -> None:
        rules = self.draft.name_rules
        target = index + delta
        if 0 <= target < len(rules):
            rules[index], rules[target] = rules[target], rules[index]
            self._rebuild("Règles par nom", self._rules)
            self._changed()

    # ================================================================ Renommage

    def _rename(self, body) -> None:
        opts = self.draft.rename

        # Aperçu en tête : on voit l'effet de chaque option en la changeant.
        preview = ctk.CTkFrame(body, fg_color=theme.ACCENT_SOFT, corner_radius=theme.RADIUS_SM)
        preview.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 0))
        preview.grid_columnconfigure(0, weight=1)
        label(preview, "Essayez avec un nom de fichier", "small", theme.MUTED).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 2))
        self.sample_var = ctk.StringVar(value="Rapport d'Été  FINAL (1).PDF")
        entry(preview, textvariable=self.sample_var).grid(row=1, column=0, sticky="ew", padx=16)
        self.preview_out = label(preview, "", "heading", theme.ACCENT)
        self.preview_out.grid(row=2, column=0, sticky="w", padx=16, pady=(10, 14))
        self.sample_var.trace_add("write", lambda *_: self._update_preview())

        r = self._setting(body, 1, "Renommer les fichiers",
                          "Désactivé, les fichiers sont rangés sous leur nom d'origine.",
                          self._switch(lambda: opts.enabled, lambda v: setattr(opts, "enabled", v)))

        def template(parent):
            var = ctk.StringVar(value=opts.template)
            var.trace_add("write", lambda *_: self._set(opts, "template", var.get()))
            return entry(parent, textvariable=var, width=240)

        r = self._setting(body, r, "Modèle de nom",
                          "{date} : date du fichier, {name} : nom nettoyé (obligatoire), {category} : catégorie. "
                          "L'extension est ajoutée automatiquement. Une date déjà présente en tête n'est "
                          "jamais ajoutée deux fois.", template)
        current_format = next((k for k, v in DATE_FORMATS.items() if v == opts.date_format), "2026-10-22")

        def date_menu(parent):
            menu = option_menu(parent, list(DATE_FORMATS), width=160,
                               command=lambda v: (setattr(opts, "date_format", DATE_FORMATS[v]), self._changed()))
            menu.set(current_format)
            return menu

        r = self._setting(body, r, "Format de la date", "", date_menu)
        sources = {"Date du fichier": "modified", "Date du jour": "today"}
        r = self._setting(body, r, "Date utilisée",
                          "La date du fichier correspond en général à la fin du téléchargement.",
                          self._segmented(list(sources), next(k for k, v in sources.items() if v == opts.date_source),
                                          lambda v: setattr(opts, "date_source", sources[v])))
        seps = {"Tiret bas  _": "_", "Tiret  -": "-"}
        r = self._setting(body, r, "Séparateur de mots", "Remplace les espaces et les caractères spéciaux.",
                          self._segmented(list(seps), next((k for k, v in seps.items() if v == opts.separator),
                                                           "Tiret bas  _"),
                                          lambda v: setattr(opts, "separator", seps[v])))
        r = self._setting(body, r, "Retirer les accents", "é devient e, œ devient oe, ß devient ss.",
                          self._switch(lambda: opts.strip_accents, lambda v: setattr(opts, "strip_accents", v)))
        r = self._setting(body, r, "Tout en minuscules", "",
                          self._switch(lambda: opts.lowercase, lambda v: setattr(opts, "lowercase", v)))
        self._setting(body, r, "Retirer les marques de copie",
                      "Supprime « (1) », « - Copie », « _copy » ajoutés par le navigateur ou l'explorateur.",
                      self._switch(lambda: opts.remove_copy_suffix,
                                   lambda v: setattr(opts, "remove_copy_suffix", v)))
        self._update_preview()

    def _update_preview(self) -> None:
        if not hasattr(self, "preview_out") or not self.preview_out.winfo_exists():
            return
        sample = self.sample_var.get().strip() or "fichier.pdf"
        try:
            result = renamer.preview(sample, self.draft.rename)
        except Exception as exc:  # noqa: BLE001 - modèle en cours de saisie
            result = f"Modèle invalide : {exc}"
        self.preview_out.configure(text=result)

    # ================================================================ Avancé

    def _advanced(self, body) -> None:
        d = self.draft
        r = self._setting(body, 0, "Ranger les dossiers entrants",
                          "Un dossier qui apparaît dans le dossier surveillé est déplacé tel quel ici.",
                          self._switch(lambda: d.folders.move, lambda v: setattr(d.folders, "move", v)))
        r = self._setting(body, r, "Destination des dossiers", "",
                          lambda p: PathField(p, d.folders.target, lambda v: self._set(d.folders, "target", v)),
                          stacked=True)
        r = self._setting(body, r, "Décompresser les archives",
                          "Les .zip et .tar sont rangés dans Archives, et leur contenu est extrait dans le "
                          "dossier ci-dessous. Les .rar et .7z sont rangés sans être décompressés.",
                          self._switch(lambda: d.archives.auto_extract,
                                       lambda v: setattr(d.archives, "auto_extract", v)))
        r = self._setting(body, r, "Destination des contenus décompressés", "",
                          lambda p: PathField(p, d.archives.extract_to,
                                              lambda v: self._set(d.archives, "extract_to", v)), stacked=True)
        r = self._setting(body, r, "Archive à la corbeille après décompression",
                          "Sinon, l'archive d'origine est conservée dans Archives.",
                          self._switch(lambda: d.archives.trash_after_extract,
                                       lambda v: setattr(d.archives, "trash_after_extract", v)))

        def max_size(parent):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            var = ctk.StringVar(value=str(d.archives.max_extract_mb))

            def changed(*_):
                if var.get().isdigit() and int(var.get()) > 0:
                    d.archives.max_extract_mb = int(var.get())
                    self._changed()

            var.trace_add("write", changed)
            entry(frame, textvariable=var, width=90).pack(side="left")
            label(frame, "Mo", "body", theme.MUTED).pack(side="left", padx=(6, 0))
            return frame

        r = self._setting(body, r, "Taille maximale décompressée",
                          "Protège contre les archives piégées qui occupent des Go une fois ouvertes.", max_size)
        r = self._setting(body, r, "Détecter les doublons",
                          "Un fichier au contenu identique à un fichier déjà rangé part dans le dossier des "
                          "doublons. Rien n'est supprimé.",
                          self._switch(lambda: d.duplicates.detect, lambda v: setattr(d.duplicates, "detect", v)))
        r = self._setting(body, r, "Dossier des doublons", "",
                          lambda p: PathField(p, d.duplicates.folder,
                                              lambda v: self._set(d.duplicates, "folder", v)), stacked=True)

        def list_entry(attr: str):
            def factory(parent):
                var = ctk.StringVar(value=", ".join(getattr(d, attr)))
                var.trace_add("write", lambda *_: (setattr(d, attr, _split_list(var.get())), self._changed()))
                return entry(parent, textvariable=var)
            return factory

        r = self._setting(body, r, "Extensions de téléchargement en cours",
                          "Ces fichiers ne sont jamais touchés : ils seront traités une fois renommés par le "
                          "navigateur.", list_entry("temp_extensions"), stacked=True)
        r = self._setting(body, r, "Fichiers toujours ignorés",
                          "Motifs de noms à ne jamais déplacer (fichiers cachés, verrous Office…).",
                          list_entry("ignore_patterns"), stacked=True)

        def ignored(parent):
            count = len(self.app.engine.ignored)
            return secondary_button(parent, f"Les proposer de nouveau ({count})", self._clear_ignored,
                                    state="normal" if count else "disabled")

        r = self._setting(body, r, "Fichiers refusés",
                          "Les fichiers ignorés ou restaurés ne sont plus proposés tant qu'ils ne changent pas.",
                          ignored)

        def places(parent):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            secondary_button(frame, "Configuration", lambda: open_in_file_manager(config_dir()),
                             icon="folder").pack(side="left")
            secondary_button(frame, "Journal technique", lambda: open_in_file_manager(log_dir()),
                             icon="folder").pack(side="left", padx=(8, 0))
            return frame

        self._setting(body, r, "Fichiers de l'application", "Réglages, historique et journal technique.", places)

    def _clear_ignored(self) -> None:
        self.app.engine.clear_ignored()
        self.app.toast("Les fichiers refusés seront de nouveau proposés lors de la prochaine analyse.")
        self.after(300, lambda: self._rebuild("Avancé", self._advanced))

    # ================================================================ brouillon

    def _set(self, obj, attr: str, value) -> None:
        setattr(obj, attr, value)
        self._changed()

    def _changed(self) -> None:
        self._set_dirty(True)
        self._update_preview()

    def _set_dirty(self, dirty: bool) -> None:
        self.dirty = dirty
        self.dirty_label.configure(text="Modifications non enregistrées" if dirty else "")
        self.save_btn.configure(state="normal" if dirty else "disabled")
        self.revert_btn.configure(state="normal" if dirty else "disabled")

    def _save(self) -> None:
        errors = validate(self.draft)
        if errors:
            self.errors_text.configure(text="Impossible d'enregistrer :\n• " + "\n• ".join(errors))
            self.errors.grid(row=1, column=0, sticky="ew", padx=theme.PAD, pady=(12, 0))
            return
        self.errors.grid_forget()
        self.app.apply_settings(self.draft.copy())
        self._set_dirty(False)
        self.app.toast("Réglages enregistrés", "success")

    def _revert(self) -> None:
        self.app.reset_view("settings")

    def can_leave(self) -> bool:
        if not self.dirty:
            return True
        return ConfirmDialog.ask(self, "Abandonner les modifications ?",
                                 "Les changements faits dans les réglages n'ont pas été enregistrés.",
                                 "Abandonner", danger=True)
