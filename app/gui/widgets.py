"""Composants réutilisables de l'interface."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import filedialog

import customtkinter as ctk

from app.gui import icons, theme


class Panel(ctk.CTkFrame):
    """Surface de contenu."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("fg_color", theme.PANEL)
        kwargs.setdefault("corner_radius", theme.RADIUS)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.LINE)
        super().__init__(master, **kwargs)


class Tab(ctk.CTkFrame):
    """Liseré vertical à la couleur de la catégorie (l'« onglet » du dossier)."""

    def __init__(self, master, color: str | tuple[str, str], height: int = 36) -> None:
        super().__init__(master, width=4, height=height, corner_radius=2, fg_color=color)
        self.grid_propagate(False)


class Pill(ctk.CTkLabel):
    """Étiquette arrondie : « modifié », « doublon », « annulé »…"""

    def __init__(self, master, text: str, color: tuple[str, str] = theme.MUTED,
                 fill: tuple[str, str] = theme.RAISED) -> None:
        super().__init__(master, text=text, font=theme.small(), text_color=color, fg_color=fill,
                         corner_radius=8, height=20, padx=8)


def primary_button(master, text: str, command: Callable, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, font=theme.body_bold(),
                         fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                         text_color="#FFFFFF", corner_radius=theme.RADIUS_SM, **kwargs)


def secondary_button(master, text: str, command: Callable, icon: str | None = None, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, font=theme.body(),
                         fg_color=theme.RAISED, hover_color=theme.LINE, text_color=theme.TEXT,
                         border_width=1, border_color=theme.LINE, corner_radius=theme.RADIUS_SM,
                         image=icons.icon(icon, 16, theme.TEXT) if icon else None,
                         compound="left", **kwargs)


def ghost_button(master, text: str, command: Callable, color=theme.MUTED, icon: str | None = None,
                 **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 30)
    kwargs.setdefault("width", 10)
    return ctk.CTkButton(master, text=text, command=command, font=theme.small(),
                         fg_color="transparent", hover_color=theme.RAISED, text_color=color,
                         corner_radius=theme.RADIUS_SM,
                         image=icons.icon(icon, 14, color) if icon else None,
                         compound="left", **kwargs)


def danger_button(master, text: str, command: Callable, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, font=theme.body_bold(),
                         fg_color=theme.DANGER, hover_color=theme.DANGER_HOVER, text_color="#FFFFFF",
                         corner_radius=theme.RADIUS_SM, **kwargs)


def entry(master, **kwargs) -> ctk.CTkEntry:
    kwargs.setdefault("height", 34)
    kwargs.setdefault("font", theme.body())
    return ctk.CTkEntry(master, fg_color=theme.RAISED, border_color=theme.LINE,
                        text_color=theme.TEXT, corner_radius=theme.RADIUS_SM, border_width=1, **kwargs)


def option_menu(master, values: list[str], command: Callable | None = None, **kwargs) -> ctk.CTkOptionMenu:
    kwargs.setdefault("height", 34)
    return ctk.CTkOptionMenu(master, values=values, command=command, font=theme.body(),
                             dropdown_font=theme.body(), fg_color=theme.RAISED,
                             button_color=theme.RAISED, button_hover_color=theme.LINE,
                             text_color=theme.TEXT, dropdown_fg_color=theme.PANEL,
                             dropdown_hover_color=theme.ACCENT_SOFT, dropdown_text_color=theme.TEXT,
                             corner_radius=theme.RADIUS_SM, dynamic_resizing=False, **kwargs)


def switch(master, text: str = "", command: Callable | None = None, **kwargs) -> ctk.CTkSwitch:
    return ctk.CTkSwitch(master, text=text, command=command, font=theme.body(), text_color=theme.TEXT,
                         progress_color=theme.ACCENT, button_color="#FFFFFF",
                         button_hover_color="#F0F0F0", fg_color=theme.LINE, **kwargs)


def label(master, text: str = "", style: str = "body", color=theme.TEXT, **kwargs) -> ctk.CTkLabel:
    fonts = {
        "title": theme.title, "heading": theme.heading, "body": theme.body,
        "bold": theme.body_bold, "small": theme.small, "figure": theme.figure,
    }
    kwargs.setdefault("anchor", "w")
    kwargs.setdefault("justify", "left")
    return ctk.CTkLabel(master, text=text, font=fonts[style](), text_color=color, **kwargs)


class PathField(ctk.CTkFrame):
    """Champ de chemin + bouton « Parcourir… »."""

    def __init__(self, master, value: str, on_change: Callable[[str], None]) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.var = ctk.StringVar(value=value)
        self.var.trace_add("write", lambda *_: on_change(self.var.get()))
        self.grid_columnconfigure(0, weight=1)
        entry(self, textvariable=self.var).grid(row=0, column=0, sticky="ew")
        secondary_button(self, "Parcourir…", self._browse, width=100, height=34).grid(
            row=0, column=1, padx=(8, 0))

    def _browse(self) -> None:
        from app.system.paths import expand_path

        current = expand_path(self.var.get()) if self.var.get().strip() else None
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            initialdir=str(current) if current and current.exists() else None,
            title="Choisir un dossier",
        )
        if chosen:
            self.var.set(chosen)


class Toast(ctk.CTkFrame):
    """Message éphémère en bas de la fenêtre (confirmation, erreur)."""

    def __init__(self, master) -> None:
        super().__init__(master, fg_color=theme.TEXT, corner_radius=theme.RADIUS_SM)
        self._label = ctk.CTkLabel(self, text="", font=theme.body(), text_color=theme.BG, padx=16, pady=8)
        self._label.pack()
        self._job: str | None = None

    def show(self, message: str, level: str = "info", duration_ms: int = 3500) -> None:
        colors = {"error": theme.DANGER, "warning": theme.WARNING, "success": theme.SUCCESS}
        self.configure(fg_color=colors.get(level, theme.TEXT))
        self._label.configure(text=message, text_color="#FFFFFF" if level in colors else theme.BG)
        self.place(relx=0.5, rely=1.0, y=-24, anchor="s")
        self.lift()
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(duration_ms, self.hide)

    def hide(self) -> None:
        self._job = None
        self.place_forget()


class ConfirmDialog(ctk.CTkToplevel):
    """Boîte de confirmation modale."""

    def __init__(self, master, title: str, message: str, confirm: str, danger: bool = False) -> None:
        super().__init__(master)
        self.result = False
        self.title(title)
        self.configure(fg_color=theme.PANEL)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())

        label(self, title, "heading").pack(anchor="w", padx=24, pady=(22, 6))
        label(self, message, "body", theme.MUTED, wraplength=380).pack(anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(20, 20))
        make = danger_button if danger else primary_button
        make(row, confirm, self._ok).pack(side="right")
        secondary_button(row, "Annuler", self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self._ok())
        center_on_parent(self, master.winfo_toplevel())
        self.after(50, self._grab)

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:  # noqa: BLE001 - fenêtre déjà fermée
            pass

    def _ok(self) -> None:
        self.result = True
        self.destroy()

    @classmethod
    def ask(cls, master, title: str, message: str, confirm: str, danger: bool = False) -> bool:
        dialog = cls(master, title, message, confirm, danger)
        master.wait_window(dialog)
        return dialog.result


def center_on_parent(window, parent) -> None:
    window.update_idletasks()
    w, h = window.winfo_reqwidth(), window.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
