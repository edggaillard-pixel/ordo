"""Classement : quelle catégorie, et dans quel dossier cible ?

Ordre d'évaluation :
1. les dossiers entrants vont dans le dossier « Dossiers » (si activé) ;
2. les règles par nom, dans l'ordre de la liste (la première qui correspond
   l'emporte) ;
3. l'extension ;
4. sinon, aucune catégorie : le fichier reste où il est.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import defaults
from app.config.settings import Category, NameRule, Settings
from app.core.renamer import extension_of
from app.system.paths import expand_path

FOLDERS_CATEGORY = "Dossiers"
DUPLICATES_CATEGORY = "Doublons"


@dataclass
class Classification:
    category: str
    target_dir: Path
    rule: str | None = None


class Classifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Index extension → catégorie, construit une seule fois.
        self._by_extension: dict[str, Category] = {}
        for cat in settings.categories:
            for ext in cat.normalized_extensions():
                self._by_extension.setdefault(ext, cat)
        self._rules = [
            (rule, _compile_patterns(rule.patterns))
            for rule in settings.name_rules
            if rule.enabled and rule.patterns.strip()
        ]

    def category_for_extension(self, name: str) -> Category | None:
        ext = extension_of(name)
        if ext in self._by_extension:
            return self._by_extension[ext]
        # « photo.JPG.gz » non reconnu ? on tente la dernière extension seule.
        last = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        return self._by_extension.get(last)

    def matching_rule(self, name: str) -> NameRule | None:
        for rule, matchers in self._rules:
            if any(m(name) for m in matchers):
                return rule
        return None

    def classify(self, path: Path, is_dir: bool, when: datetime) -> Classification | None:
        name = path.name

        if is_dir:
            if not self.settings.folders.move:
                return None
            return Classification(FOLDERS_CATEGORY, expand_path(self.settings.folders.target))

        rule = self.matching_rule(name)
        if rule is not None:
            cat = self.settings.category(rule.category)
            if cat is not None:
                target = expand_path(cat.target)
                if rule.subfolder.strip():
                    target = target / _safe_subfolder(rule.subfolder)
                return Classification(cat.name, target, rule=rule.name)

        cat = self.category_for_extension(name)
        if cat is None:
            return None
        target = expand_path(cat.target) / organize_subfolder(cat.organize, name, when)
        return Classification(cat.name, target)

    def target_for_category(self, category: str, name: str, when: datetime) -> Path | None:
        """Dossier cible si l'utilisateur change la catégorie à la main."""
        if category == FOLDERS_CATEGORY:
            return expand_path(self.settings.folders.target)
        if category == DUPLICATES_CATEGORY:
            return expand_path(self.settings.duplicates.folder)
        cat = self.settings.category(category)
        if cat is None:
            return None
        return expand_path(cat.target) / organize_subfolder(cat.organize, name, when)


def organize_subfolder(mode: str, name: str, when: datetime) -> str:
    """Sous-dossier d'organisation interne (chaîne vide = à plat)."""
    if mode == defaults.ORGANIZE_YEAR_MONTH:
        return f"{when:%Y}/{when:%m}"
    if mode == defaults.ORGANIZE_EXTENSION:
        ext = extension_of(name)
        return ext.upper().replace(".", "-") if ext else "SANS_EXTENSION"
    return ""


def _safe_subfolder(value: str) -> str:
    """Empêche un sous-dossier de règle de sortir du dossier cible (« ../ »)."""
    parts = [p for p in re.split(r"[\\/]+", value.strip()) if p not in ("", ".", "..")]
    return "/".join(parts)


def _compile_patterns(patterns: str):
    matchers = []
    for raw in patterns.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        if raw.lower().startswith("re:"):
            try:
                regex = re.compile(raw[3:], re.IGNORECASE)
            except re.error:
                continue
            matchers.append(lambda name, r=regex: r.search(name) is not None)
        else:
            pattern = raw.lower()
            matchers.append(lambda name, p=pattern: fnmatch.fnmatchcase(name.lower(), p))
    return matchers
