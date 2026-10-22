from datetime import datetime

import pytest

from app.config.settings import RenameSettings
from app.core.renamer import NameContext, build_name, extension_of, remove_copy_suffix, split_name

DATE = datetime(2026, 10, 22, 11, 43)


def rename(name: str, **opts) -> str:
    return build_name(name, NameContext(DATE, "Documents"), RenameSettings(**opts))


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("Rapport d'Été  FINAL (1).PDF", "2026-10-22_rapport_d_ete_final.pdf"),
        ("photo.JPG", "2026-10-22_photo.jpg"),
        ("Cours  --  Maths___L2.docx", "2026-10-22_cours_maths_l2.docx"),
        ("Présentation - Copie.pptx", "2026-10-22_presentation.pptx"),
        ("facture (2) - Copie (3).pdf", "2026-10-22_facture.pdf"),
        ("Œuvre & Straße.txt", "2026-10-22_oeuvre_strasse.txt"),
        ("sauvegarde.TAR.GZ", "2026-10-22_sauvegarde.tar.gz"),
        ("sans_extension", "2026-10-22_sans_extension"),
        ("!!!.pdf", "2026-10-22_fichier.pdf"),
        ("CON.txt", "2026-10-22_con.txt"),
    ],
)
def test_default_rules(original: str, expected: str) -> None:
    assert rename(original) == expected


def test_existing_date_is_not_duplicated() -> None:
    assert rename("2019-05-01_Vacances.png") == "2019-05-01_vacances.png"
    assert rename("20190501 vacances.png") == "2019-05-01_vacances.png"


def test_idempotent() -> None:
    once = rename("Mon Fichier (1).PDF")
    assert rename(once) == once


def test_disabled_keeps_name() -> None:
    assert rename("Mon Fichier.PDF", enabled=False) == "Mon Fichier.PDF"


def test_options() -> None:
    assert rename("Été Rapport.pdf", strip_accents=False) == "2026-10-22_été_rapport.pdf"
    assert rename("Mon Rapport.pdf", template="{name}") == "mon_rapport.pdf"
    assert rename("Mon Rapport.pdf", template="{category}-{name}", separator="-") == "documents-mon-rapport.pdf"
    assert rename("Mon Rapport.pdf", date_format="%Y%m%d") == "20261022_mon_rapport.pdf"


def test_reserved_windows_name_without_date() -> None:
    assert rename("con.txt", template="{name}") == "con_.txt"


def test_very_long_name_fits_filesystem() -> None:
    name = rename("a" * 400 + ".pdf")
    assert name.endswith(".pdf")
    assert len(name.encode()) <= 255


def test_split_and_extension() -> None:
    assert split_name("a.tar.gz") == ("a", ".tar.gz")
    assert split_name(".bashrc") == (".bashrc", "")
    assert split_name("dossier.v2", is_dir=True) == ("dossier.v2", "")
    assert extension_of("X.PDF") == "pdf"


def test_remove_copy_suffix() -> None:
    assert remove_copy_suffix("rapport (1)") == "rapport"
    assert remove_copy_suffix("rapport_copy 2") == "rapport"
    assert remove_copy_suffix("(1)") == "(1)"
