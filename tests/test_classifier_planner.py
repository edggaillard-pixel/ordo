from datetime import datetime
from pathlib import Path

from app.config.settings import NameRule, validate
from app.core.classifier import Classifier
from app.core.models import ActionKind
from app.core.planner import Planner
from tests.conftest import make_file

WHEN = datetime(2026, 10, 22).timestamp()


def test_extension_and_organisation(settings, home: Path) -> None:
    c = Classifier(settings)
    when = datetime(2026, 10, 22)
    pdf = c.classify(Path("x/rapport.PDF"), False, when)
    assert pdf.category == "Documents"
    assert pdf.target_dir == home / "Rangement/Documents/PDF"
    img = c.classify(Path("x/photo.jpg"), False, when)
    assert img.target_dir == home / "Rangement/Images/2026/10"
    tgz = c.classify(Path("x/backup.tar.gz"), False, when)
    assert tgz.category == "Archives"
    assert c.classify(Path("x/inconnu.xyz"), False, when) is None


def test_name_rules_win_over_extension(settings, home: Path) -> None:
    c = Classifier(settings)
    found = c.classify(Path("x/Facture-EDF.pdf"), False, datetime(2026, 1, 1))
    assert found.rule == "Factures"
    assert found.target_dir == home / "Rangement/Documents/Factures"
    shot = c.classify(Path("x/Capture d’écran 2026-10-22 à 11.40.png"), False, datetime(2026, 1, 1))
    assert shot.target_dir == home / "Rangement/Images/Captures d'écran"


def test_regex_rule_and_unsafe_subfolder(settings, home: Path) -> None:
    settings.name_rules = [NameRule("Cours", r"re:^(R|SAE)\d\.\d+", "Documents", "../../Cours")]
    c = Classifier(settings)
    found = c.classify(Path("x/R3.12 CV.pdf"), False, datetime(2026, 1, 1))
    assert found.target_dir == home / "Rangement/Documents/Cours"


def test_plan_full(settings, home: Path) -> None:
    src = make_file(home / "Downloads/Rapport Final (1).PDF", mtime=WHEN)
    action = Planner(settings).plan(src)
    assert action.kind is ActionKind.MOVE
    assert action.new_name == "2026-10-22_rapport_final.pdf"
    assert action.destination == home / "Rangement/Documents/PDF/2026-10-22_rapport_final.pdf"


def test_plan_ignores(settings, home: Path) -> None:
    p = Planner(settings)
    assert p.plan(make_file(home / "Downloads/film.mp4.crdownload")) is None
    assert p.plan(make_file(home / "Downloads/.DS_Store")) is None
    assert p.plan(make_file(home / "Downloads/~$rapport.docx")) is None
    assert p.plan(make_file(home / "Downloads/truc.inconnu")) is None


def test_plan_duplicate_and_name_conflict(settings, home: Path) -> None:
    target = home / "Rangement/Documents/PDF"
    make_file(target / "ancien_nom.pdf", b"meme contenu")
    make_file(target / "2026-10-22_cours.pdf", b"autre contenu")

    dup = Planner(settings).plan(make_file(home / "Downloads/copie.pdf", b"meme contenu", mtime=WHEN))
    assert dup.kind is ActionKind.DUPLICATE
    assert dup.duplicate_of.name == "ancien_nom.pdf"
    assert dup.target_dir == home / "Rangement/_Doublons"

    other = Planner(settings).plan(make_file(home / "Downloads/cours.pdf", b"nouveau", mtime=WHEN))
    assert other.kind is ActionKind.MOVE
    assert other.new_name.startswith("2026-10-22_cours_2")  # suffixe horodaté
    assert other.new_name.endswith(".pdf")


def test_reserved_destinations(settings, home: Path) -> None:
    planner = Planner(settings)
    a = planner.plan(make_file(home / "Downloads/doc.pdf", b"1", mtime=WHEN))
    b = planner.plan(make_file(home / "Downloads/doc (1).pdf", b"2", mtime=WHEN), reserved=[a.destination])
    assert a.destination != b.destination


def test_folders_and_archives(settings, home: Path) -> None:
    folder = home / "Downloads/Projet Unity"
    make_file(folder / "a.txt")
    action = Planner(settings).plan(folder)
    assert action.kind is ActionKind.FOLDER
    assert action.target_dir == home / "Rangement/Dossiers"

    archive = Planner(settings).plan(make_file(home / "Downloads/Pack.zip", mtime=WHEN))
    assert archive.extract_to == home / "Rangement/Dossiers/2026-10-22_pack"


def test_target_inside_source_is_protected(settings, home: Path) -> None:
    settings.categories[0].target = str(home / "Downloads/Documents")
    (home / "Downloads/Documents").mkdir()
    assert Planner(settings).plan(home / "Downloads/Documents") is None


def test_validation(settings) -> None:
    assert validate(settings) == []
    settings.rename.template = "{date}_{nom}"
    settings.categories[1].extensions.append("pdf")
    errors = validate(settings)
    assert any("{name}" in e for e in errors)
    assert any(".pdf" in e for e in errors)
    assert any("{nom}" in e for e in errors)


def test_settings_roundtrip(settings, tmp_path: Path) -> None:
    from app.config.settings import SettingsStore

    store = SettingsStore(tmp_path / "cfg")
    settings.mode = "auto"
    store.save(settings)
    loaded = store.load()
    assert loaded.to_dict() == settings.to_dict()

    # Ancien fichier incomplet + clé inconnue : valeurs par défaut pour le reste.
    store.path.write_text('{"mode": "auto", "cle_obsolete": 1, "rename": {"separator": "-"}}', encoding="utf-8")
    partial = store.load()
    assert partial.mode == "auto" and partial.rename.separator == "-" and partial.rename.enabled
    assert len(partial.categories) == 8

    store.path.write_text("{pas du json", encoding="utf-8")
    assert store.load().mode == "review"
    assert store.path.with_suffix(".invalide.json").exists()
