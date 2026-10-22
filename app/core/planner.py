"""Planification : transforme une entrée du dossier surveillé en proposition.

Le planificateur ne touche à rien sur le disque (il lit seulement). Il répond
à la question « que ferait-on de ce fichier ? » ; l'exécuteur, lui, agit.
Cette séparation permet l'écran *À valider* : on montre le plan, l'utilisateur
corrige, puis on exécute.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from pathlib import Path

from app.config.settings import Settings
from app.core import conflicts, renamer
from app.core.classifier import DUPLICATES_CATEGORY, Classifier
from app.core.models import ActionKind, PlannedAction, fingerprint
from app.core.stability import has_temp_extension
from app.fs import archives
from app.system.paths import expand_path


class Planner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.classifier = Classifier(settings)
        self._protected = [_norm(p) for p in settings.protected_paths()]

    # ------------------------------------------------------------ filtres

    def should_ignore(self, path: Path) -> bool:
        """Fichiers à ne jamais toucher : temporaires, cachés, système…"""
        name = path.name
        if has_temp_extension(name, self.settings.temp_extensions):
            return True
        lower = name.lower()
        for pattern in self.settings.ignore_patterns:
            if fnmatch.fnmatchcase(lower, pattern.lower()):
                return True
        # Un dossier cible placé DANS le dossier surveillé ne doit pas être
        # pris pour un nouveau dossier entrant.
        here = _norm(path)
        for protected in self._protected:
            if protected == here or protected.startswith(here + os.sep):
                return True
        return path.is_symlink()

    # ------------------------------------------------------------ plan

    def plan(self, path: Path, reserved: Iterable[Path] = ()) -> PlannedAction | None:
        """Proposition pour ``path``, ou ``None`` s'il faut le laisser en place."""
        if self.should_ignore(path) or not path.exists():
            return None

        is_dir = path.is_dir()
        when = renamer.file_date(path, self.settings.rename)
        found = self.classifier.classify(path, is_dir, when)
        if found is None:
            return None  # extension inconnue : on n'y touche pas

        new_name = renamer.build_name(
            path.name, renamer.NameContext(when, found.category), self.settings.rename, is_dir=is_dir
        )

        action = PlannedAction(
            source=path,
            kind=ActionKind.FOLDER if is_dir else ActionKind.MOVE,
            target_dir=found.target_dir,
            new_name=new_name,
            category=found.category,
            rule=found.rule,
            source_fingerprint=fingerprint(path),
        )

        if not is_dir:
            self.check_duplicate(action)
            if action.kind is ActionKind.MOVE:
                self._plan_extraction(action, reserved)

        action.new_name = conflicts.resolve_conflict(
            action.target_dir, action.new_name, is_dir=is_dir, reserved=reserved
        )
        return action

    def check_duplicate(self, action: PlannedAction) -> None:
        """Redirige vers le dossier des doublons si le contenu existe déjà."""
        if not self.settings.duplicates.detect or action.is_dir:
            return
        original = conflicts.find_duplicate(action.source, action.target_dir)
        if original is None:
            return
        action.kind = ActionKind.DUPLICATE
        action.duplicate_of = original
        action.target_dir = expand_path(self.settings.duplicates.folder)
        action.category = DUPLICATES_CATEGORY
        action.extract_to = None

    def _plan_extraction(self, action: PlannedAction, reserved: Iterable[Path]) -> None:
        cfg = self.settings.archives
        if not cfg.auto_extract:
            return
        if not archives.is_supported(renamer.extension_of(action.source.name)):
            return
        folder_name, _ = renamer.split_name(action.new_name)
        base = expand_path(cfg.extract_to)
        action.extract_to = base / conflicts.resolve_conflict(base, folder_name, is_dir=True, reserved=reserved)

    def retarget(self, action: PlannedAction, category: str) -> None:
        """L'utilisateur change la catégorie dans l'écran de validation."""
        when = renamer.file_date(action.source, self.settings.rename)
        target = self.classifier.target_for_category(category, action.source.name, when)
        if target is None:
            return
        action.category = category
        action.target_dir = target
        action.kind = (
            ActionKind.FOLDER if action.is_dir
            else ActionKind.DUPLICATE if category == DUPLICATES_CATEGORY
            else ActionKind.MOVE
        )
        if action.kind is not ActionKind.DUPLICATE:
            action.duplicate_of = None


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
