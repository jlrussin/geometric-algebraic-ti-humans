"""Downloading, verifying and cropping the Experiment 1 images."""

from __future__ import annotations

import hashlib
import io
import re
import tempfile
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from geo_alg_ti_humans import cli, images


@pytest.fixture(scope="session")
def archive(request) -> Path:
    """The clip-art archive, downloaded once into pytest's cache and reused by later runs."""
    cache = request.config.cache.mkdir("clipart_archive")
    path = cache / images.ARCHIVE_NAME
    if not path.is_file():
        # Downloaded beside the cache entry, verified, then moved into place in one step.
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            downloaded = images.download(Path(tmp))
            images.verify(downloaded)
            downloaded.replace(path)
    return path


def read_digests(repo_root) -> list[tuple[str, str]]:
    """The (digest, path) pairs of ``media.sha256``, in file order."""
    text = (repo_root / "experiments" / "experiment1" / "media.sha256").read_text()
    return [tuple(line.split(maxsplit=1)) for line in text.splitlines()]


def test_digest_list_names_80_distinct_images(repo_root):
    """``media.sha256`` is in shasum format, sorted, with one line per image and no repeats."""
    text = (repo_root / "experiments" / "experiment1" / "media.sha256").read_text()
    lines = text.splitlines()
    assert all(re.fullmatch(r"[0-9a-f]{64}  media/pps/[A-Za-z]+_C\.jpg", line) for line in lines)
    paths = [path for _, path in read_digests(repo_root)]
    assert len(paths) == 80 and len(set(paths)) == 80
    assert paths == sorted(paths)


def test_verify_rejects_a_wrong_digest(tmp_path):
    """Any file other than the published archive fails verification."""
    path = tmp_path / images.ARCHIVE_NAME
    path.write_bytes(b"not the archive")
    with pytest.raises(ValueError):
        images.verify(path)


def test_images_command_refuses_a_wrong_archive(tmp_path, capsys):
    """``images --archive`` with the wrong file exits with status 1 and says why."""
    path = tmp_path / images.ARCHIVE_NAME
    path.write_bytes(b"not the archive")
    assert cli.main(["images", "--archive", str(path)]) == 1
    assert images.ARCHIVE_SHA256 in capsys.readouterr().err


def _small_archive(path: Path, names) -> dict[str, str]:
    """A zip of one synthetic image per name, as the archive lays them out; return the digest
    each cropped image has."""
    digests = {}
    with zipfile.ZipFile(path, "w") as zf:
        for i, name in enumerate(names):
            img = Image.new("RGB", (60, 40), "white")
            img.paste((20 * i, 0, 0), (10, 10, 30 + i, 30))
            raw = io.BytesIO()
            img.save(raw, "JPEG", quality=95)
            zf.writestr(f"Clipart_JPG/{name}", raw.getvalue())
            cropped = io.BytesIO()
            with Image.open(io.BytesIO(raw.getvalue())) as stored:
                images.crop_and_square(stored).save(cropped, "JPEG", quality=95)
            digests[name] = hashlib.sha256(cropped.getvalue()).hexdigest()
    return digests


@pytest.fixture
def small_archive(tmp_path, monkeypatch) -> tuple[Path, dict[str, str]]:
    """A two-image archive that ``build`` accepts in place of the published one."""
    path = tmp_path / images.ARCHIVE_NAME
    digests = _small_archive(path, ["A_C.jpg", "B_C.jpg"])
    monkeypatch.setattr(images, "verify", lambda archive: None)
    monkeypatch.setattr(images, "_expected_digests", lambda: dict(digests))
    return path, digests


def test_build_replaces_the_images_and_keeps_the_other_files(tmp_path, small_archive):
    """Each image replaces the file of its name; the folder's other files stay as they were."""
    archive, digests = small_archive
    media_dir = tmp_path / "media" / "pps"
    media_dir.mkdir(parents=True)
    (media_dir / "A_C.jpg").write_bytes(b"an earlier image")
    (media_dir / "other.jpg").write_bytes(b"another file")
    written = images.build(media_dir, archive=archive)
    assert written == [media_dir / name for name in digests]
    assert {p.name: images._sha256(p) for p in written} == digests
    assert sorted(p.name for p in media_dir.iterdir()) == ["A_C.jpg", "B_C.jpg", "other.jpg"]
    assert (media_dir / "other.jpg").read_bytes() == b"another file"
    assert sorted(p.name for p in media_dir.parent.iterdir()) == ["pps"]


def test_build_keeps_a_link_and_updates_the_folder_it_points_to(tmp_path, small_archive):
    """A ``media_dir`` that is a symbolic link stays a link; the folder it points to gets the
    images and keeps its other files."""
    archive, digests = small_archive
    target = tmp_path / "elsewhere" / "pps"
    target.mkdir(parents=True)
    (target / "other.jpg").write_bytes(b"another file")
    media_dir = tmp_path / "media" / "pps"
    media_dir.parent.mkdir()
    media_dir.symlink_to(target, target_is_directory=True)
    images.build(media_dir, archive=archive)
    assert media_dir.is_symlink() and media_dir.resolve() == target.resolve()
    assert sorted(p.name for p in target.iterdir()) == ["A_C.jpg", "B_C.jpg", "other.jpg"]
    assert {name: images._sha256(target / name) for name in digests} == digests
    assert sorted(p.name for p in target.parent.iterdir()) == ["pps"]


@pytest.mark.parametrize("failure", ["digest", "missing image", "rename", "interruption"])
def test_build_leaves_the_folder_as_it_was_on_failure(tmp_path, monkeypatch, small_archive,
                                                      failure):
    """A wrong digest, an image missing from the archive, or a failure or an interruption
    while the new folder takes the old one's place leaves the old folder in place, unchanged."""
    archive, digests = small_archive
    media_dir = tmp_path / "media" / "pps"
    media_dir.mkdir(parents=True)
    (media_dir / "A_C.jpg").write_bytes(b"an earlier image")
    if failure == "digest":
        monkeypatch.setattr(images, "_expected_digests", lambda: {**digests, "B_C.jpg": "0" * 64})
        error = ValueError
    elif failure == "missing image":
        monkeypatch.setattr(images, "_expected_digests", lambda: {**digests, "C_C.jpg": "0" * 64})
        error = KeyError
    else:
        error = OSError if failure == "rename" else KeyboardInterrupt
        rename = Path.rename

        def stop_before_the_new_folder_is_in_place(self, target):
            if self.name == "new":
                raise error()
            return rename(self, target)

        monkeypatch.setattr(Path, "rename", stop_before_the_new_folder_is_in_place)
    with pytest.raises(error):
        images.build(media_dir, archive=archive)
    assert [(p.name, p.read_bytes()) for p in media_dir.iterdir()] == [
        ("A_C.jpg", b"an earlier image")]
    assert sorted(p.name for p in media_dir.parent.iterdir()) == ["pps"]


@pytest.mark.parametrize(("contents", "message"), [
    ("not a zip file", "images: File is not a zip file\n"),
    ("an archive without the images", "images: There is no item named 'Clipart_JPG/"),
])
def test_images_command_reports_an_unreadable_archive(tmp_path, monkeypatch, capsys, contents,
                                                       message):
    """An archive that is not a zip file, or lacks an image, ends the command with a message,
    and nothing is created."""
    import geo_alg_ti_humans

    path = tmp_path / images.ARCHIVE_NAME
    if contents == "not a zip file":
        path.write_bytes(b"not a zip file")
    else:
        _small_archive(path, ["A_C.jpg"])
    monkeypatch.setattr(images, "verify", lambda archive: None)
    monkeypatch.setattr(geo_alg_ti_humans, "REPO_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").touch()
    assert cli.main(["images", "--archive", str(path)]) == 1
    assert capsys.readouterr().err.startswith(message)
    assert sorted(p.name for p in tmp_path.iterdir()) == [images.ARCHIVE_NAME, "pyproject.toml"]


def test_crop_and_square_on_a_synthetic_image():
    """A 100 x 40 block gets margins of 5 and 2, then sits centered on a 110 x 110 square."""
    img = Image.new("RGB", (200, 100), "white")
    img.paste((200, 30, 30), (50, 20, 150, 60))
    out = images.crop_and_square(img)
    assert out.size == (110, 110)
    content = ImageChops.difference(out.convert("RGB"), Image.new("RGB", out.size, "white"))
    assert content.getbbox() == (5, 35, 105, 75)


def test_crop_and_square_counts_235_as_content():
    """White means every channel above 235: a (235, 235, 235) pixel is content, 236 is not."""
    img = Image.new("RGB", (50, 50), "white")
    img.putpixel((10, 10), (235, 235, 235))
    img.putpixel((40, 40), (236, 236, 236))
    out = images.crop_and_square(img)
    assert out.size == (1, 1) and out.getpixel((0, 0)) == (235, 235, 235)


def test_crop_and_square_keeps_the_content_centered_at_an_edge():
    """Content 3 pixels from the left edge gets a margin of 3 on both sides, not 5."""
    img = Image.new("RGB", (200, 200), "white")
    img.paste((0, 0, 0), (3, 50, 103, 150))
    out = images.crop_and_square(img)
    assert out.size == (110, 110)
    content = ImageChops.difference(out.convert("RGB"), Image.new("RGB", out.size, "white"))
    assert content.getbbox() == (5, 5, 105, 105)


def test_crop_and_square_rejects_a_white_image():
    """An image with no content has nothing to crop to."""
    with pytest.raises(ValueError):
        images.crop_and_square(Image.new("RGB", (20, 20), "white"))


def test_build_reproduces_the_deployed_images(tmp_path, repo_root, archive):
    """The 80 cropped images match the sha256 digests of the files participants saw."""
    written = images.build(tmp_path, archive=archive)
    assert len(written) == 80
    expected = {path.removeprefix("media/pps/"): digest for digest, path in read_digests(repo_root)}
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in written}
    assert actual == expected
