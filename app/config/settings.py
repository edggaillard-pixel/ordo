"""Réglages de l'application : modèle typé, validation, persistance JSON.

Le fichier ``settings.json`` est écrit de façon atomique (fichier temporaire
puis remplacement), si bien qu'un plantage pendant l'écriture ne peut pas le
corrompre. À la lecture, les clés manquantes reprennent leur valeur par défaut
et les clés inconnues sont ignorées : un ancien fichier reste compatible avec
une nouvelle version de l'application.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from app.config import defaults
from app.system.paths import config_dir, expand_path

log = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"

MODE_REVIEW = "review"  # chaque fichier attend une validation
MODE_AUTO = "auto"      # rangement immédiat


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------

@dataclass
class Category:
    name: str
    extensions: list[str]
    target: str
    organize: str = defaults.ORGANIZE_NONE
    color: str = "#4F7DF3"

    def normalized_extensions(self) -> list[str]:
        """Extensions en minuscules, sans point initial ni doublon."""
        seen: list[str] = []
        for ext in self.extensions:
            ext = ext.strip().lower().lstrip(".")
            if ext and ext not in seen:
                seen.append(ext)
        return seen


@dataclass
class NameRule:
    name: str
    patterns: str
    category: str
    subfolder: str = ""
    enabled: bool = True


@dataclass
class RenameSettings:
    enabled: bool = True
    # Jetons disponibles : {date}, {name}, {category}. L'extension est
    # toujours ajoutée automatiquement à la fin.
    template: str = "{date}_{name}"
    date_format: str = "%Y-%m-%d"
    date_source: str = "modified"  # "modified" (date du fichier) ou "today"
    separator: str = "_"
    lowercase: bool = True
    strip_accents: bool = True
    remove_copy_suffix: bool = True  # « rapport (1).pdf », « x - Copie.docx »


@dataclass
class DuplicateSettings:
    detect: bool = True
    folder: str = "{documents}/Ordo/_Doublons"


@dataclass
class FolderSettings:
    move: bool = True
    target: str = "{documents}/Ordo/Dossiers"


@dataclass
class ArchiveSettings:
    auto_extract: bool = True
    extract_to: str = "{documents}/Ordo/Dossiers"
    trash_after_extract: bool = False
    max_extract_mb: int = 4096  # garde-fou contre les « bombes zip »


@dataclass
class Settings:
    source_dir: str = "{downloads}"
    mode: str = MODE_REVIEW
    watching_enabled: bool = False
    start_watching_on_launch: bool = True
    stability_seconds: float = 3.0
    notifications: bool = True
    start_with_system: bool = False
    close_to_tray: bool = True
    appearance: str = "dark"  # "dark", "light" ou "system"
    temp_extensions: list[str] = field(default_factory=lambda: list(defaults.DEFAULT_TEMP_EXTENSIONS))
    ignore_patterns: list[str] = field(default_factory=lambda: list(defaults.DEFAULT_IGNORE_PATTERNS))
    categories: list[Category] = field(
        default_factory=lambda: [Category(**c) for c in copy.deepcopy(defaults.DEFAULT_CATEGORIES)]
    )
    name_rules: list[NameRule] = field(
        default_factory=lambda: [NameRule(**r) for r in copy.deepcopy(defaults.DEFAULT_NAME_RULES)]
    )
    rename: RenameSettings = field(default_factory=RenameSettings)
    duplicates: DuplicateSettings = field(default_factory=DuplicateSettings)
    folders: FolderSettings = field(default_factory=FolderSettings)
    archives: ArchiveSettings = field(default_factory=ArchiveSettings)

    # ----------------------------------------------------------------- accès

    @property
    def source_path(self) -> Path:
        return expand_path(self.source_dir)

    def category(self, name: str) -> Category | None:
        for cat in self.categories:
            if cat.name == name:
                return cat
        return None

    def protected_paths(self) -> list[Path]:
        """Tous les dossiers que l'application écrit.

        Si l'un d'eux se trouve dans le dossier surveillé, il ne doit jamais
        être pris pour un « nouveau dossier » à ranger.
        """
        paths = [expand_path(c.target) for c in self.categories]
        paths += [
            expand_path(self.duplicates.folder),
            expand_path(self.folders.target),
            expand_path(self.archives.extract_to),
        ]
        return paths

    def copy(self) -> "Settings":
        return copy.deepcopy(self)

    # ----------------------------------------------------- (dé)sérialisation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        base = cls()
        nested = {
            "rename": RenameSettings,
            "duplicates": DuplicateSettings,
            "folders": FolderSettings,
            "archives": ArchiveSettings,
        }
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in known:
                continue  # clé obsolète ou inconnue
            if key in nested and isinstance(value, dict):
                setattr(base, key, _build(nested[key], value))
            elif key == "categories" and isinstance(value, list):
                base.categories = [_build(Category, c) for c in value if isinstance(c, dict)]
            elif key == "name_rules" and isinstance(value, list):
                base.name_rules = [_build(NameRule, r) for r in value if isinstance(r, dict)]
            else:
                setattr(base, key, value)
        return base


def _build(klass, data: dict[str, Any]):
    """Instancie une dataclass en ignorant les clés inconnues."""
    allowed = {f.name for f in fields(klass)}
    return klass(**{k: v for k, v in data.items() if k in allowed})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_TEMPLATE_TOKENS = {"date", "name", "category"}


def validate(settings: Settings) -> list[str]:
    """Renvoie la liste des erreurs, vide si les réglages sont cohérents."""
    errors: list[str] = []

    if not settings.source_dir.strip():
        errors.append("Le dossier surveillé est vide.")
    elif not settings.source_path.is_dir():
        errors.append(f"Le dossier surveillé n'existe pas : {settings.source_path}")

    if settings.mode not in (MODE_REVIEW, MODE_AUTO):
        errors.append("Mode de fonctionnement inconnu.")

    if not 0.5 <= float(settings.stability_seconds) <= 600:
        errors.append("Le délai de stabilité doit être compris entre 0,5 et 600 secondes.")

    # Catégories : noms uniques, cibles renseignées, extensions sans conflit.
    names: set[str] = set()
    owner: dict[str, str] = {}
    for cat in settings.categories:
        label = cat.name.strip()
        if not label:
            errors.append("Une catégorie n'a pas de nom.")
            continue
        if label.lower() in names:
            errors.append(f"La catégorie « {label} » existe en double.")
        names.add(label.lower())
        if not cat.target.strip():
            errors.append(f"La catégorie « {label} » n'a pas de dossier cible.")
        if cat.organize not in defaults.ORGANIZE_LABELS:
            errors.append(f"Organisation inconnue pour « {label} ».")
        for ext in cat.normalized_extensions():
            if ext in owner and owner[ext] != label:
                errors.append(f"L'extension .{ext} est dans « {owner[ext]} » et dans « {label} ».")
            owner[ext] = label

    # Règles par nom.
    for rule in settings.name_rules:
        if not rule.patterns.strip():
            errors.append(f"La règle « {rule.name or 'sans nom'} » n'a pas de motif.")
        if settings.category(rule.category) is None:
            errors.append(f"La règle « {rule.name or 'sans nom'} » vise une catégorie inconnue : {rule.category}.")
        for pattern in _split_patterns(rule.patterns):
            if pattern.lower().startswith("re:"):
                try:
                    re.compile(pattern[3:])
                except re.error as exc:
                    errors.append(f"Expression régulière invalide dans « {rule.name} » : {exc}")

    # Modèle de renommage.
    template = settings.rename.template
    tokens = set(re.findall(r"\{(\w*)\}", template))
    if "name" not in tokens:
        errors.append("Le modèle de renommage doit contenir {name}.")
    unknown = tokens - _TEMPLATE_TOKENS
    if unknown:
        errors.append("Jeton(s) inconnu(s) dans le modèle : " + ", ".join("{" + t + "}" for t in sorted(unknown)))
    try:
        from datetime import datetime
        datetime(2026, 1, 1).strftime(settings.rename.date_format)
    except (ValueError, TypeError):
        errors.append("Format de date invalide.")

    for label, value in (
        ("dossier des doublons", settings.duplicates.folder),
        ("dossier des dossiers", settings.folders.target),
        ("dossier d'extraction", settings.archives.extract_to),
    ):
        if not value.strip():
            errors.append(f"Le {label} est vide.")

    # Aucune cible ne doit être le dossier surveillé lui-même (boucle infinie).
    if settings.source_dir.strip():
        source = _safe_resolve(settings.source_path)
        for target in settings.protected_paths():
            if _safe_resolve(target) == source:
                errors.append(f"Un dossier cible est identique au dossier surveillé : {target}")
                break

    return errors


def _split_patterns(patterns: str) -> list[str]:
    return [p.strip() for p in patterns.split(";") if p.strip()]


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


# ---------------------------------------------------------------------------
# Persistance
# ---------------------------------------------------------------------------

class SettingsStore:
    """Lit et écrit ``settings.json`` dans le dossier de configuration."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or config_dir()
        self.path = self.directory / SETTINGS_FILENAME

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return Settings.from_dict(data)
        except (OSError, ValueError, TypeError) as exc:
            # Fichier illisible : on le met de côté au lieu de l'écraser.
            backup = self.path.with_suffix(".invalide.json")
            log.error("Réglages illisibles (%s), copie conservée dans %s", exc, backup)
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            return Settings()

    def save(self, settings: Settings) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=".settings-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
