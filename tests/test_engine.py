"""Tests de bout en bout : vrai watchdog, vrais fichiers, vrais threads."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest

from app.config.settings import MODE_AUTO
from app.core.engine import Engine
from tests.conftest import make_file, wait_until


@pytest.fixture()
def engine(settings, tmp_path: Path):
    notifications: list[tuple[str, str]] = []
    eng = Engine(settings, tmp_path / "data", notify=lambda t, m: notifications.append((t, m)))
    eng.notifications = notifications  # type: ignore[attr-defined]
    eng.start()
    yield eng
    eng.shutdown()


def drain(engine: Engine) -> list:
    events = []
    while not engine.events.empty():
        events.append(engine.events.get_nowait())
    return events


def start_watching(engine: Engine) -> None:
    engine.set_watching(True)
    assert wait_until(lambda: engine.watching, 5)


def test_review_mode_waits_for_download_then_validates(engine, home: Path) -> None:
    make_file(home / "Downloads/deja_la.pdf")  # présent avant : pas touché
    start_watching(engine)

    # Simule Chrome : écriture dans .crdownload puis renommage final.
    part = home / "Downloads/Cours Réseaux.pdf.crdownload"
    make_file(part, b"debut")
    time.sleep(0.3)
    with part.open("ab") as fh:
        fh.write(b" suite")
    part.rename(home / "Downloads/Cours Réseaux.pdf")

    assert wait_until(lambda: engine.pending_count() == 1, 8)
    action = engine.pending()[0]
    assert action.source.name == "Cours Réseaux.pdf"
    assert action.new_name.endswith("_cours_reseaux.pdf")

    engine.approve([action.id])
    assert wait_until(lambda: action.destination.exists(), 5)
    assert not (home / "Downloads/Cours Réseaux.pdf").exists()
    assert (home / "Downloads/deja_la.pdf").exists()
    assert engine.stats.sorted_today == 1
    assert wait_until(lambda: any("à valider" in m for _, m in engine.notifications), 5)


def test_edit_then_reject(engine, home: Path) -> None:
    start_watching(engine)
    make_file(home / "Downloads/a.pdf", b"a")
    make_file(home / "Downloads/b.png", b"b")
    assert wait_until(lambda: engine.pending_count() == 2, 8)
    by_name = {a.source.name: a for a in engine.pending()}

    # « Non, celui-là on change » : nouveau nom + autre catégorie.
    engine.update_pending(by_name["a.pdf"].id, new_name="mon_cv.pdf", category="Code")
    edited = next(a for a in engine.pending() if a.id == by_name["a.pdf"].id)
    assert edited.user_edited and edited.destination == home / "Rangement/Code/PDF/mon_cv.pdf"

    engine.reject([by_name["b.png"].id])
    engine.approve([edited.id])
    assert wait_until(lambda: (home / "Rangement/Code/PDF/mon_cv.pdf").exists(), 5)
    assert wait_until(lambda: engine.pending_count() == 0, 5)

    # Le fichier ignoré n'est plus proposé, même par « Analyser le dossier ».
    engine.scan_now()
    time.sleep(1)
    assert engine.pending_count() == 0
    assert (home / "Downloads/b.png").exists()


def test_auto_mode_duplicates_and_undo(engine, settings, home: Path) -> None:
    settings.mode = MODE_AUTO
    engine.apply_settings(settings)
    start_watching(engine)

    make_file(home / "Downloads/photo.jpg", b"pixels")
    assert wait_until(lambda: engine.stats.sorted_today == 1, 8)
    make_file(home / "Downloads/photo (1).jpg", b"pixels")
    assert wait_until(lambda: engine.stats.duplicates_today == 1, 8)
    assert len(list((home / "Rangement/_Doublons").iterdir())) == 1

    batches = engine.journal.batches()
    assert len(batches) == 2
    first = batches[-1]  # le plus ancien : photo.jpg
    engine.undo(first.id)
    assert wait_until(lambda: (home / "Downloads/photo.jpg").exists(), 5)
    # Restauré dans le dossier surveillé, mais pas rangé de nouveau.
    time.sleep(2)
    assert (home / "Downloads/photo.jpg").exists()
    assert engine.journal.batches()[-1].undone


def test_scan_existing_always_goes_to_review(engine, settings, home: Path) -> None:
    settings.mode = MODE_AUTO
    engine.apply_settings(settings)
    make_file(home / "Downloads/old.docx")
    make_file(home / "Downloads/notes.inconnu")
    engine.scan_now()
    assert wait_until(lambda: engine.pending_count() == 1, 5)
    assert (home / "Downloads/old.docx").exists()


def test_zip_is_sorted_and_extracted(engine, home: Path) -> None:
    start_watching(engine)
    z = home / "Downloads/Pack Textures.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("textures/sol.png", "x")
    assert wait_until(lambda: engine.pending_count() == 1, 8)
    action = engine.pending()[0]
    engine.approve([action.id])
    assert wait_until(lambda: (home / "Rangement/Archives").exists(), 5)
    extracted = list((home / "Rangement/Dossiers").iterdir())
    assert wait_until(lambda: len(list((home / "Rangement/Dossiers").iterdir())) == 1, 5)
    extracted = list((home / "Rangement/Dossiers").iterdir())
    assert (extracted[0] / "sol.png").exists()

    # L'annulation remet l'archive et retire le dossier extrait (corbeille).
    batch = engine.journal.batches()[0]
    engine.undo(batch.id)
    assert wait_until(lambda: z.exists(), 5)


def test_incoming_folder_is_moved(engine, home: Path) -> None:
    start_watching(engine)
    folder = home / "Downloads/Projet"
    make_file(folder / "main.py", "print()")
    assert wait_until(lambda: engine.pending_count() == 1, 8)
    action = engine.pending()[0]
    assert action.is_dir
    engine.approve([action.id])
    assert wait_until(lambda: (home / "Rangement/Dossiers" / action.new_name / "main.py").exists(), 5)


def test_pending_disappears_when_file_deleted(engine, home: Path) -> None:
    start_watching(engine)
    f = make_file(home / "Downloads/temp.pdf")
    assert wait_until(lambda: engine.pending_count() == 1, 8)
    f.unlink()
    assert wait_until(lambda: engine.pending_count() == 0, 6)

# GROGNON
