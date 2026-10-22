"""Fenêtre principale : barre latérale, navigation, liaison avec le moteur.

La fenêtre ne fait aucun travail sur le disque. Elle envoie des commandes au
moteur et lit ses événements toutes les 150 ms (``_poll``), dans le thread Tk.
"""

from __future__ import annotations

import logging
import queue
import sys
from collections.abc import Callable

import customtkinter as ctk

from app import APP_NAME
from app.config import defaults
from app.config.settings import Settings, SettingsStore
from app.core.classifier import DUPLICATES_CATEGORY, FOLDERS_CATEGORY
from app.core.engine import Engine
from app.gui import icons, theme
from app.gui.tray import TrayIcon, tray_supported
from app.gui.views.dashboard import DashboardView
from app.gui.views.history import HistoryView
from app.gui.views.review import ReviewView
from app.gui.views.settings_view import SettingsView
from app.gui.widgets import Toast, label, switch
from app.system import autostart
from app.system.notifier import Notifier
from app.system.paths import contract_path, resource_path

log = logging.getLogger(__name__)

POLL_MS = 150

VIEWS = {
    "dashboard": ("Tableau de bord", "dashboard", DashboardView),
    "review": ("À valider", "inbox", ReviewView),
    "history": ("Historique", "history", HistoryView),
    "settings": ("Réglages", "settings", SettingsView),
}


class NavItem(ctk.CTkFrame):
    """Entrée de la barre latérale : icône, libellé, compteur facultatif."""

    def __init__(self, master, text: str, icon_name: str, command: Callable[[], None]) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=theme.RADIUS_SM, height=40, cursor="hand2")
        self.command = command
        self.icon_name = icon_name
        self.selected = False
        self.grid_columnconfigure(1, weight=1)
        self.icon = ctk.CTkLabel(self, text="", image=icons.icon(icon_name, 18, theme.MUTED), width=20)
        self.icon.grid(row=0, column=0, padx=(12, 10), pady=9)
        self.text = label(self, text, "body", theme.MUTED)
        self.text.grid(row=0, column=1, sticky="w")
        self.badge = ctk.CTkLabel(self, text="", font=theme.font(11, "bold"), text_color="#FFFFFF",
                                  fg_color=theme.ACCENT, corner_radius=9, height=18, width=24)
        for widget in (self, self.icon, self.text, self.badge):
            widget.bind("<Button-1>", lambda _e: self.command())
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))

    def _hover(self, inside: bool) -> None:
        if not self.selected:
            self.configure(fg_color=theme.RAISED if inside else "transparent")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        color = theme.ACCENT if selected else theme.MUTED
        self.configure(fg_color=theme.ACCENT_SOFT if selected else "transparent")
        self.text.configure(text_color=theme.TEXT if selected else theme.MUTED,
                            font=theme.body_bold() if selected else theme.body())
        self.icon.configure(image=icons.icon(self.icon_name, 18, color))

    def set_badge(self, count: int) -> None:
        if count:
            self.badge.configure(text=str(count) if count < 100 else "99+")
            self.badge.grid(row=0, column=2, padx=(0, 10))
        else:
            self.badge.grid_forget()


class AppWindow(ctk.CTk):
    def __init__(self, settings: Settings, store: SettingsStore, engine: Engine, notifier: Notifier,
                 start_minimized: bool = False) -> None:
        ctk.set_appearance_mode(settings.appearance)
        super().__init__(fg_color=theme.BG)
        self.settings = settings
        self.store = store
        self.engine = engine
        self.notifier = notifier
        self.ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._background_hint_shown = False
        self._quitting = False
        self.tray: TrayIcon | None = None

        self.title(APP_NAME)
        self.geometry("1180x760")
        self.minsize(1000, 660)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.views: dict[str, ctk.CTkFrame] = {}
        self.current: str | None = None
        self.toast_widget = Toast(self)

        # Zone de notification (sauf macOS).
        if tray_supported():
            tray = TrayIcon(
                self.ui_queue, on_open=self.bring_to_front, on_toggle=self._toggle_from_tray,
                is_watching=lambda: self.engine.watching, pending_count=self.engine.pending_count,
                on_review=lambda: (self.bring_to_front(), self.show("review")), on_quit=self.quit_app,
            )
            if tray.start():
                self.tray = tray
                self.notifier.tray_notify = tray.notify

        self.show("dashboard")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_all("<Control-q>", lambda _e: self.quit_app())
        self.after(300, self._set_window_icon)  # après l'icône par défaut de CustomTkinter
        self.after(POLL_MS, self._poll)

        if settings.start_watching_on_launch or start_minimized:
            self.engine.set_watching(True)
        if start_minimized:
            self.after(10, self.withdraw if self.tray else self.iconify)

    @property
    def tray_available(self) -> bool:
        return self.tray is not None

    # ================================================================ barre latérale

    def _build_sidebar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=theme.SIDEBAR, corner_radius=0, width=236)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(2, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 26))
        logo = ctk.CTkImage(light_image=icons.app_logo(72), dark_image=icons.app_logo(72), size=(36, 36))
        ctk.CTkLabel(brand, text="", image=logo).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        label(brand, APP_NAME, "heading").grid(row=0, column=1, sticky="sw")
        label(brand, "Rangement automatique", "small", theme.MUTED).grid(row=1, column=1, sticky="nw")

        nav = ctk.CTkFrame(bar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=12)
        nav.grid_columnconfigure(0, weight=1)
        self.nav_items: dict[str, NavItem] = {}
        for index, (key, (text, icon_name, _)) in enumerate(VIEWS.items()):
            item = NavItem(nav, text, icon_name, lambda k=key: self.show(k))
            item.grid(row=index, column=0, sticky="ew", pady=2)
            self.nav_items[key] = item

        # Interrupteur principal, toujours visible.
        card = ctk.CTkFrame(bar, fg_color=theme.PANEL, corner_radius=theme.RADIUS,
                            border_width=1, border_color=theme.LINE)
        card.grid(row=3, column=0, sticky="ew", padx=14, pady=16)
        card.grid_columnconfigure(0, weight=1)
        label(card, "Surveillance", "bold").grid(row=0, column=0, sticky="w", padx=16, pady=(14, 0))
        self.watch_switch = switch(card, command=self._toggle_watch, switch_width=46, switch_height=24, width=46)
        self.watch_switch.grid(row=0, column=1, rowspan=2, padx=(4, 14), pady=(14, 0), sticky="e")
        self.watch_status = label(card, "", "small", theme.MUTED)
        self.watch_status.grid(row=1, column=0, sticky="w", padx=16)
        self.watch_detail = label(card, "", "small", theme.FAINT, wraplength=180)
        self.watch_detail.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(6, 14))
        self._render_watch_state(False)

    def _render_watch_state(self, watching: bool, error: str | None = None) -> None:
        if watching:
            self.watch_switch.select()
            self.watch_status.configure(text="● Active", text_color=theme.SUCCESS)
            self.watch_detail.configure(text=f"Surveille {contract_path(self.settings.source_path)}")
        else:
            self.watch_switch.deselect()
            self.watch_status.configure(text="● En pause", text_color=theme.MUTED)
            self.watch_detail.configure(text=error or "Les nouveaux fichiers ne sont pas traités.")
            if error:
                self.watch_detail.configure(text_color=theme.DANGER)
        if watching or not error:
            self.watch_detail.configure(text_color=theme.FAINT)
        if self.tray:
            self.tray.refresh()

    def _toggle_watch(self) -> None:
        enabled = bool(self.watch_switch.get())
        self.engine.set_watching(enabled)
        self.settings.watching_enabled = enabled
        self.store.save(self.settings)

    def _toggle_from_tray(self) -> None:
        if self.engine.watching:
            self.watch_switch.deselect()
        else:
            self.watch_switch.select()
        self._toggle_watch()

    # ================================================================ navigation

    def show(self, key: str) -> None:
        if key == self.current:
            return
        current_view = self.views.get(self.current) if self.current else None
        if current_view is not None and hasattr(current_view, "can_leave") and not current_view.can_leave():
            return
        if current_view is not None:
            current_view.grid_forget()
            if self.current == "settings":  # brouillon abandonné : on repart de zéro
                self.views.pop("settings").destroy()
        view = self.views.get(key)
        if view is None:
            view = VIEWS[key][2](self.content, self)
            self.views[key] = view
        elif hasattr(view, "refresh"):
            view.refresh()
        view.grid(row=0, column=0, sticky="nsew")
        self.current = key
        for name, item in self.nav_items.items():
            item.set_selected(name == key)

    def reset_view(self, key: str) -> None:
        view = self.views.pop(key, None)
        if view is not None:
            view.destroy()
        self.current = None
        self.show(key)

    def toast(self, message: str, level: str = "info") -> None:
        self.toast_widget.show(message, level)

    def category_color(self, category: str | None):
        if category == FOLDERS_CATEGORY:
            return defaults.FOLDERS_COLOR
        if category == DUPLICATES_CATEGORY:
            return defaults.DUPLICATES_COLOR
        cat = self.settings.category(category) if category else None
        return cat.color if cat else theme.FAINT

    # ================================================================ réglages

    def apply_settings(self, new: Settings) -> None:
        old = self.settings
        new.watching_enabled = self.engine.watching
        self.store.save(new)
        self.settings = new
        self.engine.apply_settings(new.copy())
        if new.start_with_system != old.start_with_system:
            try:
                autostart.set_enabled(new.start_with_system)
            except OSError as exc:
                self.toast(f"Lancement avec l'ordinateur impossible : {exc}", "error")
        if new.appearance != old.appearance:
            ctk.set_appearance_mode(new.appearance)
        self._render_watch_state(self.engine.watching)
        for key in ("dashboard", "review"):
            if key in self.views:
                self.views[key].refresh()

    # ================================================================ boucle d'événements

    def _poll(self) -> None:
        try:
            self._drain_engine()
            while True:
                try:
                    self.ui_queue.get_nowait()()
                except queue.Empty:
                    break
        except Exception:  # noqa: BLE001 - une erreur d'affichage ne doit pas tout bloquer
            log.exception("Erreur pendant la mise à jour de l'interface")
        if not self._quitting:
            self.after(POLL_MS, self._poll)

    def _drain_engine(self) -> None:
        refresh_review = refresh_dashboard = refresh_history = False
        for _ in range(500):  # borne : ne jamais geler l'interface
            try:
                event = self.engine.events.get_nowait()
            except queue.Empty:
                break
            kind = event.kind
            if kind == "status":
                self._render_watch_state(event.data.get("watching", False), event.data.get("error"))
                if event.data.get("error"):
                    self.toast(event.data["error"], "error")
            elif kind == "pending":
                refresh_review = refresh_dashboard = True
            elif kind == "activity":
                if "dashboard" in self.views:
                    self.views["dashboard"].add_activity(event.data["item"])
                if event.data["item"].level == "error":
                    self.toast(event.data["item"].message, "error")
            elif kind in ("stats",):
                refresh_dashboard = True
            elif kind == "history":
                refresh_history = refresh_dashboard = True
            elif kind == "scan":
                added = event.data.get("added", 0)
                if added:
                    self.toast(f"{added} fichier{'s' if added > 1 else ''} à valider")
                    self.show("review")
                else:
                    self.toast("Rien de nouveau à ranger dans le dossier.")

        if refresh_review:
            self.nav_items["review"].set_badge(self.engine.pending_count())
            if self.current == "review":
                self.views["review"].refresh()
            if self.tray:
                self.tray.refresh()
        if refresh_dashboard and "dashboard" in self.views and self.current == "dashboard":
            self.views["dashboard"].refresh()
        if refresh_history and "history" in self.views:
            if self.current == "history":
                self.views["history"].refresh()

    # ================================================================ fenêtre

    def _set_window_icon(self) -> None:
        try:
            from PIL import ImageTk

            self._icon_image = ImageTk.PhotoImage(icons.app_logo(64))
            self.iconphoto(True, self._icon_image)
            ico = resource_path("assets/icon.ico")
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(str(ico))
        except Exception:  # noqa: BLE001
            log.debug("Icône de fenêtre non appliquée", exc_info=True)

    def bring_to_front(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    def on_close(self) -> None:
        if not self.settings.close_to_tray:
            self.quit_app()
            return
        if self.tray is not None:
            self.withdraw()
            if not self._background_hint_shown:
                self._background_hint_shown = True
                self.tray.notify(APP_NAME, "Ordo continue de surveiller en arrière-plan. "
                                           "Clic droit sur l'icône pour quitter.")
        else:
            self.iconify()

    def quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.settings.watching_enabled = self.engine.watching
        try:
            self.store.save(self.settings)
        except OSError:
            log.exception("Sauvegarde des réglages à la fermeture")
        self.engine.shutdown()
        if self.tray:
            self.tray.stop()
        self.destroy()
