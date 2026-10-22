"""Décompression automatique des archives ZIP et TAR.

Sécurité avant tout, puisque les archives viennent d'Internet :

- **zip slip** : un membre nommé ``../../.bashrc`` ne peut pas sortir du
  dossier d'extraction ;
- **bombe zip** : la taille décompressée annoncée est plafonnée ;
- les liens symboliques et fichiers spéciaux des TAR sont refusés ;
- l'extraction se fait dans un dossier temporaire, renommé seulement une
  fois terminée : jamais de dossier à moitié rempli.

Si l'archive ne contient qu'un dossier racine (cas fréquent : ``projet.zip``
contient ``projet/``), son contenu est remonté d'un niveau pour éviter
``projet/projet/``.

Formats pris en charge : .zip, .tar, .tar.gz/.tgz, .tar.bz2, .tar.xz.
Les .rar et .7z sont rangés mais pas décompressés (pas de bibliothèque
standard pour ces formats).
"""

from __future__ import annotations

import shutil
import tarfile
import uuid
import zipfile
from pathlib import Path

SUPPORTED_EXTENSIONS = ("zip", "tar", "tgz", "tar.gz", "tar.bz2", "tar.xz")


class ArchiveError(Exception):
    pass


def is_supported(extension: str) -> bool:
    return extension.lower().lstrip(".") in SUPPORTED_EXTENSIONS


def extract(archive: Path, destination: Path, max_bytes: int) -> Path:
    """Décompresse ``archive`` dans le dossier ``destination`` (qui ne doit pas exister)."""
    if destination.exists():
        raise ArchiveError(f"Le dossier d'extraction existe déjà : {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".ordo-extract-{uuid.uuid4().hex[:8]}")
    staging.mkdir()
    try:
        if zipfile.is_zipfile(archive):
            _extract_zip(archive, staging, max_bytes)
        elif tarfile.is_tarfile(archive):
            _extract_tar(archive, staging, max_bytes)
        else:
            raise ArchiveError("Format d'archive non reconnu ou fichier corrompu.")

        root = _single_root(staging)
        if root is not None:
            root.rename(destination)
            staging.rmdir()
        else:
            staging.rename(destination)
        return destination
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _check_inside(base: Path, member_name: str) -> Path:
    target = (base / member_name).resolve()
    if not target.is_relative_to(base.resolve()):
        raise ArchiveError(f"Chemin dangereux dans l'archive : {member_name}")
    return target


def _extract_zip(archive: Path, staging: Path, max_bytes: int) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            total = sum(m.file_size for m in members)
            if total > max_bytes:
                raise ArchiveError(_too_big(total, max_bytes))
            for member in members:
                _check_inside(staging, member.filename)
            zf.extractall(staging)
    except (zipfile.BadZipFile, RuntimeError) as exc:  # RuntimeError : zip chiffré
        raise ArchiveError(f"Archive illisible ou protégée par mot de passe ({exc}).") from exc


def _extract_tar(archive: Path, staging: Path, max_bytes: int) -> None:
    try:
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            total = 0
            for member in members:
                if not (member.isfile() or member.isdir()):
                    raise ArchiveError(f"Élément non autorisé dans l'archive : {member.name}")
                _check_inside(staging, member.name)
                total += member.size
            if total > max_bytes:
                raise ArchiveError(_too_big(total, max_bytes))
            # Le filtre « data » (Python ≥ 3.12) ajoute ses propres contrôles.
            if hasattr(tarfile, "data_filter"):
                tf.extractall(staging, members=members, filter="data")
            else:  # pragma: no cover - anciens Python
                tf.extractall(staging, members=members)
    except tarfile.TarError as exc:
        raise ArchiveError(f"Archive illisible ({exc}).") from exc


def _single_root(staging: Path) -> Path | None:
    children = [c for c in staging.iterdir() if c.name not in ("__MACOSX", ".DS_Store")]
    junk = [c for c in staging.iterdir() if c not in children]
    if len(children) == 1 and children[0].is_dir():
        for item in junk:  # métadonnées macOS inutiles
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
        return children[0]
    return None


def _too_big(total: int, limit: int) -> str:
    mb = 1024 * 1024
    return f"Archive trop volumineuse une fois décompressée ({total // mb} Mo, limite {limit // mb} Mo)."
