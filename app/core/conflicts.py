"""Doublons et conflits de noms.

Deux situations différentes :

- **vrai doublon** : un fichier au contenu identique (même empreinte SHA-256)
  existe déjà dans le dossier cible. Le nouveau fichier part dans le dossier
  des doublons ; rien n'est jamais supprimé ;
- **conflit de nom** : un fichier différent porte déjà ce nom. Le nouveau
  reçoit un suffixe horodaté : ``rapport_20261022-114305.pdf``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from app.core.renamer import split_name

_CHUNK = 1024 * 1024
# On ne compare pas un fichier à plus de N candidats de même taille : protège
# contre un dossier cible énorme rempli de fichiers identiques en taille.
MAX_CANDIDATES = 200


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicate(source: Path, target_dir: Path) -> Path | None:
    """Cherche dans ``target_dir`` un fichier au contenu identique à ``source``.

    Comparaison en deux temps : la taille d'abord (immédiat), puis l'empreinte
    SHA-256 seulement pour les fichiers de même taille.
    """
    try:
        size = source.stat().st_size
    except OSError:
        return None
    if not target_dir.is_dir():
        return None

    candidates: list[Path] = []
    try:
        with os.scandir(target_dir) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False) and entry.stat().st_size == size:
                        candidates.append(Path(entry.path))
                except OSError:
                    continue
                if len(candidates) >= MAX_CANDIDATES:
                    break
    except OSError:
        return None

    if not candidates:
        return None
    source_hash = file_hash(source)
    for candidate in candidates:
        try:
            if file_hash(candidate) == source_hash:
                return candidate
        except OSError:
            continue
    return None


def resolve_conflict(
    target_dir: Path,
    name: str,
    is_dir: bool = False,
    reserved: Iterable[Path] = (),
    now: datetime | None = None,
) -> str:
    """Renvoie un nom libre dans ``target_dir``.

    ``reserved`` contient les destinations déjà promises à d'autres fichiers en
    attente de validation, pour que deux propositions ne visent pas le même nom.
    """
    taken = {os.path.normcase(str(p)) for p in reserved}

    def free(candidate: str) -> bool:
        path = target_dir / candidate
        return not path.exists() and os.path.normcase(str(path)) not in taken

    if free(name):
        return name

    stem, ext = split_name(name, is_dir)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    candidate = f"{stem}_{stamp}{ext}"
    counter = 2
    while not free(candidate):
        candidate = f"{stem}_{stamp}_{counter}{ext}"
        counter += 1
    return candidate
