"""Normalisation des noms de fichiers.

Exemple avec les réglages par défaut (date du fichier : 22/10/2026) :

    « Rapport d'Été  FINAL (1).PDF »  →  « 2026-10-22_rapport_d_ete_final.pdf »

Étapes, dans l'ordre :
1. séparation nom / extension (en gérant ``.tar.gz``) ;
2. suppression des suffixes de copie : `` (1)``, `` - Copie``, ``_copy``… ;
3. détection d'une date déjà présente en tête (pour ne pas en ajouter une 2e) ;
4. translittération des accents (é → e, œ → oe, ß → ss…) ;
5. minuscules, puis tout caractère hors lettres/chiffres → séparateur ;
6. application du modèle (``{date}_{name}`` par défaut) ;
7. garde-fous système : noms réservés Windows, 255 octets maximum.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config.defaults import COMPOUND_EXTENSIONS
from app.config.settings import RenameSettings

# Limite technique des systèmes de fichiers (NTFS, APFS, ext4) : 255 octets.
MAX_NAME_BYTES = 255

_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# Lettres que la décomposition Unicode ne sait pas simplifier seule.
_SPECIAL_LETTERS = str.maketrans({
    "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "þ": "th", "Þ": "TH", "ð": "d",
    "’": "'", "‘": "'", "–": "-", "—": "-",
})

# Suffixes ajoutés par les navigateurs et les explorateurs de fichiers.
_COPY_SUFFIX = re.compile(
    r"""(
        \s*\(\d{1,3}\)                        # « (1) »
      | \s*[-_]\s*(copie|copy|kopie|copia)(\s*\(?\d+\)?)?   # « - Copie », « _copy 2 »
      | \s+(copie|copy)(\s*\d+)?              # « copie 2 »
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

# Date en tête de nom : 2026-10-22, 2026_10_22, 2026.10.22, 20261022.
_LEADING_DATE = re.compile(
    r"^(?P<y>(19|20)\d{2})[-_. ]?(?P<m>0[1-9]|1[0-2])[-_. ]?(?P<d>0[1-9]|[12]\d|3[01])(?=$|[^0-9])"
)


def split_name(name: str, is_dir: bool = False) -> tuple[str, str]:
    """Sépare le nom et l'extension (avec le point). Les dossiers n'en ont pas."""
    if is_dir:
        return name, ""
    lower = name.lower()
    for ext in COMPOUND_EXTENSIONS:
        if lower.endswith(ext) and len(name) > len(ext):
            return name[: -len(ext)], name[-len(ext):]
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:  # « fichier » ou « .bashrc »
        return name, ""
    return stem, "." + ext


def extension_of(name: str) -> str:
    """Extension en minuscules, sans le point : « tar.gz », « pdf », ou «  »."""
    return split_name(name)[1].lower().lstrip(".")


def strip_accents(text: str) -> str:
    text = text.translate(_SPECIAL_LETTERS)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def remove_copy_suffix(stem: str) -> str:
    original, previous = stem, None
    while previous != stem:  # « x (1) - Copie » → « x »
        previous = stem
        stem = _COPY_SUFFIX.sub("", stem).rstrip()
    return stem or original  # « (1).pdf » ne devient pas un nom vide


def clean_text(text: str, opts: RenameSettings) -> str:
    """Accents, casse et caractères spéciaux d'un fragment de nom."""
    if opts.strip_accents:
        text = strip_accents(text)
    if opts.lowercase:
        text = text.lower()
    sep = opts.separator or "_"
    # \w couvre lettres et chiffres de toutes les langues ; « _ » est traité
    # comme un séparateur comme les autres pour éviter « a__b ».
    text = re.sub(r"[\W_]+", sep, text, flags=re.UNICODE)
    return text.strip(sep)


@dataclass
class NameContext:
    """Informations disponibles pour le modèle de nom."""

    date: datetime
    category: str | None = None


def build_name(original: str, ctx: NameContext, opts: RenameSettings, is_dir: bool = False) -> str:
    """Calcule le nouveau nom d'un fichier (ou dossier) selon les réglages."""
    if not opts.enabled:
        return original

    stem, ext = split_name(original, is_dir)
    if opts.remove_copy_suffix:
        stem = remove_copy_suffix(stem)

    sep = opts.separator or "_"
    template = opts.template

    # Si le nom commence déjà par une date, on la garde (normalisée) au lieu
    # d'en ajouter une seconde : renommer deux fois donne le même résultat.
    date_match = _LEADING_DATE.match(stem.strip())
    if date_match and "{date}" in template:
        existing = datetime(int(date_match["y"]), int(date_match["m"]), int(date_match["d"]))
        date_text = existing.strftime(opts.date_format)
        stem = stem.strip()[date_match.end():]
    else:
        date_text = ctx.date.strftime(opts.date_format)

    name_part = clean_text(stem, opts) or ("dossier" if is_dir else "fichier")
    category_part = clean_text(ctx.category or "", opts)

    values = {
        "date": clean_text(date_text, _keep_digits(opts)) if date_text else "",
        "name": name_part,
        "category": category_part,
    }
    result = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), ""), template)
    # Un jeton vide (catégorie absente…) ne doit pas laisser « __ » ou « _x ».
    result = re.sub(re.escape(sep) + "{2,}", sep, result).strip(sep + " ") or name_part

    ext = _clean_extension(ext, opts)
    result = _avoid_reserved(result, sep)
    return _fit_length(result, ext)


def _keep_digits(opts: RenameSettings) -> RenameSettings:
    """La date garde ses tirets : « 2026-10-22 » et non « 2026_10_22 »."""
    return RenameSettings(
        enabled=True, separator="-", lowercase=opts.lowercase,
        strip_accents=opts.strip_accents,
    )


def _clean_extension(ext: str, opts: RenameSettings) -> str:
    if not ext:
        return ""
    body = re.sub(r"[^\w.]+", "", ext.lstrip("."), flags=re.UNICODE)
    if opts.lowercase:
        body = body.lower()
    return "." + body if body else ""


def _avoid_reserved(stem: str, sep: str) -> str:
    if stem.lower() in _WINDOWS_RESERVED:
        return stem + sep
    return stem


def _fit_length(stem: str, ext: str) -> str:
    """Tronque le nom (jamais l'extension) au-delà de 255 octets."""
    budget = MAX_NAME_BYTES - len(ext.encode("utf-8"))
    encoded = stem.encode("utf-8")
    if len(encoded) > budget:
        stem = encoded[:budget].decode("utf-8", errors="ignore")
    return stem + ext


def file_date(path: Path, opts: RenameSettings) -> datetime:
    """Date utilisée pour {date} : date de modification ou date du jour."""
    if opts.date_source == "today":
        return datetime.now()
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return datetime.now()


def preview(original: str, opts: RenameSettings, category: str | None = "Documents") -> str:
    """Aperçu utilisé par l'écran Réglages, avec la date du jour."""
    return build_name(original, NameContext(datetime.now(), category), opts)

# GROGNON
