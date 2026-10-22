"""Valeurs par défaut : catégories, règles par nom, extensions temporaires.

Tout ce qui est ici est modifiable depuis l'écran Réglages ; ces valeurs ne
servent qu'au premier lancement (ou quand un réglage manque dans le JSON).
"""

from __future__ import annotations

# Modes d'organisation interne d'un dossier cible.
ORGANIZE_NONE = "none"            # tout à plat dans le dossier
ORGANIZE_YEAR_MONTH = "year_month"  # 2026/10/
ORGANIZE_EXTENSION = "extension"  # PDF/, DOCX/…

ORGANIZE_LABELS = {
    ORGANIZE_NONE: "Aucun sous-dossier",
    ORGANIZE_YEAR_MONTH: "Par année / mois",
    ORGANIZE_EXTENSION: "Par extension",
}

# Extensions composées, reconnues avant l'extension simple
# (« sauvegarde.tar.gz » a pour extension « .tar.gz », pas « .gz »).
COMPOUND_EXTENSIONS = (
    ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst",
)

DEFAULT_CATEGORIES: list[dict] = [
    {
        "name": "Documents",
        "color": "#4F7DF3",
        "extensions": [
            "pdf", "doc", "docx", "odt", "rtf", "txt", "md", "tex",
            "xls", "xlsx", "ods", "csv", "ppt", "pptx", "odp",
            "epub", "pages", "numbers", "key",
        ],
        "target": "{documents}/Ordo/Documents",
        "organize": ORGANIZE_EXTENSION,
    },
    {
        "name": "Images",
        "color": "#2FB37A",
        "extensions": [
            "jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic",
            "heif", "tif", "tiff", "ico", "raw", "cr2", "nef", "arw", "psd",
        ],
        "target": "{pictures}/Ordo",
        "organize": ORGANIZE_YEAR_MONTH,
    },
    {
        "name": "Vidéos",
        "color": "#D9668F",
        "extensions": ["mp4", "mkv", "avi", "mov", "wmv", "webm", "flv", "m4v", "mpg", "mpeg"],
        "target": "{videos}/Ordo",
        "organize": ORGANIZE_YEAR_MONTH,
    },
    {
        "name": "Audio",
        "color": "#9B6CF0",
        "extensions": ["mp3", "wav", "flac", "aac", "ogg", "m4a", "wma", "opus", "mid", "midi"],
        "target": "{music}/Ordo",
        "organize": ORGANIZE_NONE,
    },
    {
        "name": "Archives",
        "color": "#E5A23A",
        "extensions": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "tgz", "tar.gz", "tar.bz2", "tar.xz", "iso"],
        "target": "{documents}/Ordo/Archives",
        "organize": ORGANIZE_NONE,
    },
    {
        "name": "Code",
        "color": "#37B6C9",
        "extensions": [
            "py", "ipynb", "js", "ts", "jsx", "tsx", "html", "css", "scss",
            "json", "xml", "yml", "yaml", "toml", "ini", "java", "kt", "c",
            "cpp", "h", "hpp", "cs", "php", "rb", "go", "rs", "swift", "sh",
            "bat", "ps1", "sql", "puml", "unity", "unitypackage",
        ],
        "target": "{documents}/Ordo/Code",
        "organize": ORGANIZE_EXTENSION,
    },
    {
        "name": "Installeurs",
        "color": "#8B93A1",
        "extensions": ["exe", "msi", "dmg", "pkg", "deb", "rpm", "appimage", "apk", "jar"],
        "target": "{documents}/Ordo/Installeurs",
        "organize": ORGANIZE_NONE,
    },
    {
        "name": "Polices",
        "color": "#C9A227",
        "extensions": ["ttf", "otf", "woff", "woff2"],
        "target": "{documents}/Ordo/Polices",
        "organize": ORGANIZE_NONE,
    },
]

# Règles par nom : évaluées dans l'ordre, AVANT les règles d'extension.
# Syntaxe des motifs : jokers (* et ?), plusieurs motifs séparés par « ; »,
# ou une expression régulière préfixée par « re: ». Insensible à la casse.
DEFAULT_NAME_RULES: list[dict] = [
    {
        "name": "Factures",
        "enabled": True,
        "patterns": "*facture*;*invoice*",
        "category": "Documents",
        "subfolder": "Factures",
    },
    {
        "name": "Captures d'écran",
        "enabled": True,
        "patterns": "capture d*;screenshot*;screen shot*",
        "category": "Images",
        "subfolder": "Captures d'écran",
    },
]

# Fichiers en cours de téléchargement (Chrome/Edge, Firefox, Safari, Opera,
# µTorrent, Internet Explorer, fichiers temporaires génériques).
DEFAULT_TEMP_EXTENSIONS = [
    "crdownload", "part", "partial", "download", "opdownload",
    "!ut", "!qb", "tmp", "temp", "filepart",
]

# Fichiers système ou verrous que l'on ne touche jamais.
DEFAULT_IGNORE_PATTERNS = [
    ".*",            # fichiers cachés (.DS_Store, .localized…)
    "~$*",           # verrous Microsoft Office
    "desktop.ini",
    "Thumbs.db",
    "*.lnk",         # raccourcis Windows
]

# Couleurs des pseudo-catégories.
FOLDERS_COLOR = "#6C8EBF"
DUPLICATES_COLOR = "#E5534B"

# GROGNON
