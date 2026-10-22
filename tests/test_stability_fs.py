import tarfile
import zipfile
from pathlib import Path

import pytest

from app.core.stability import StabilityTracker
from app.fs import archives
from app.fs.file_ops import DestinationExists, safe_move
from tests.conftest import make_file


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_stable_after_delay(tmp_path: Path) -> None:
    clock = Clock()
    tracker = StabilityTracker(3, ["part"], clock=clock)
    f = make_file(tmp_path / "a.pdf", b"x")
    tracker.touch(f)
    assert tracker.poll() == []      # première mesure
    clock.t = 2
    assert tracker.poll() == []      # pas encore 3 s
    f.write_bytes(b"xx")             # le fichier grossit
    clock.t = 4
    assert tracker.poll() == []      # changement : le délai repart
    clock.t = 7.1
    assert tracker.poll() == [f]
    assert len(tracker) == 0


def test_firefox_placeholder_waits_for_part(tmp_path: Path) -> None:
    clock = Clock()
    tracker = StabilityTracker(1, ["part"], clock=clock)
    placeholder = make_file(tmp_path / "video.mp4", b"")
    part = make_file(tmp_path / "video.mp4.part", b"data")
    tracker.touch(placeholder)
    tracker.poll()
    clock.t = 5
    assert tracker.poll() == []
    part.unlink()
    clock.t = 10
    assert tracker.poll() == [placeholder]


def test_deleted_file_is_forgotten(tmp_path: Path) -> None:
    tracker = StabilityTracker(0, [])
    f = make_file(tmp_path / "a.txt")
    tracker.touch(f)
    f.unlink()
    assert tracker.poll() == [] and len(tracker) == 0


def test_safe_move_never_overwrites(tmp_path: Path) -> None:
    src = make_file(tmp_path / "a.txt", "nouveau")
    dst = make_file(tmp_path / "out/a.txt", "ancien")
    with pytest.raises(DestinationExists):
        safe_move(src, dst)
    assert dst.read_text() == "ancien" and src.exists()

    moved = safe_move(src, tmp_path / "out/sub/b.txt")
    assert moved.read_text() == "nouveau" and not src.exists()


def test_safe_move_directory(tmp_path: Path) -> None:
    make_file(tmp_path / "d/x.txt")
    safe_move(tmp_path / "d", tmp_path / "out/d2")
    assert (tmp_path / "out/d2/x.txt").exists()


def test_extract_zip_flattens_single_root(tmp_path: Path) -> None:
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("projet/a.txt", "a")
        zf.writestr("projet/src/b.py", "b")
        zf.writestr("__MACOSX/._a.txt", "junk")
    out = archives.extract(z, tmp_path / "out/projet", 10_000)
    assert (out / "a.txt").exists() and (out / "src/b.py").exists()
    assert not (out / "projet").exists()


def test_extract_rejects_zip_slip_and_bombs(tmp_path: Path) -> None:
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    with pytest.raises(archives.ArchiveError):
        archives.extract(evil, tmp_path / "out/evil", 10_000)
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "out/evil").exists()

    big = tmp_path / "big.zip"
    with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.bin", b"\0" * 50_000)
    with pytest.raises(archives.ArchiveError):
        archives.extract(big, tmp_path / "out/big", 1_000)
    assert list((tmp_path / "out").iterdir()) == []  # pas de dossier temporaire oublié


def test_extract_tar_rejects_symlinks(tmp_path: Path) -> None:
    t = tmp_path / "a.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        info = tarfile.TarInfo("lien")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)
    with pytest.raises(archives.ArchiveError):
        archives.extract(t, tmp_path / "out/a", 10_000)
