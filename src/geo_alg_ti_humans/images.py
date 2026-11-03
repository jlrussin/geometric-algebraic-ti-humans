"""The 80 Experiment 1 images, cropped from the PicturePerfectSet clip-art collection.

The collection (Saryazdi, Bannon, Rodrigues, Klammer, & Chambers, 2018, Behavior Research
Methods, 50, 2498-2510, https://doi.org/10.3758/s13428-018-1028-5) is not redistributed with
this code. ``build`` downloads the authors' archive, checks its sha256 digest, and crops each
image the experiment uses. A pixel is white background when all three channels are above 235;
the content is the tight box around every other pixel. Each axis gets a margin of ``int(0.05 *
content size)`` on both sides, cut to the room available on the side with less of it, so the
content stays centered. The crop is pasted at ``((side - width) // 2, (side - height) // 2)`` on
a white square whose side is the longer of the two, and saved as JPEG at quality 95. The output
is byte-identical to the images participants saw, whose names and sha256 digests are listed in
``experiments/experiment1/media.sha256``.
"""

from __future__ import annotations

import functools
import hashlib
import io
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

from geo_alg_ti_humans import REPO_ROOT

ARCHIVE_NAME = "Clipart_JPG.zip"
ARCHIVE_URL = (
    "https://drive.usercontent.google.com/download"
    "?id=1TPltUXRQPKt2qMzIxeu27LwiWkRRJdbl&export=download&confirm=t"
)
ARCHIVE_SHA256 = "6bae15e82da7efa38dc43f3ad05e4828eee53a9a0533fbc0a43e166df0c58909"
WHITE_THRESHOLD = 235

_DIGESTS = REPO_ROOT / "experiments" / "experiment1" / "media.sha256"


def download(dest: Path) -> Path:
    """Download the archive into the directory ``dest`` and return its path."""
    path = dest / ARCHIVE_NAME
    with urllib.request.urlopen(ARCHIVE_URL, timeout=60) as response, path.open("wb") as out:
        shutil.copyfileobj(response, out)
    return path


def verify(path: Path) -> None:
    """Raise ``ValueError`` unless the archive's sha256 digest is ``ARCHIVE_SHA256``."""
    digest = _sha256(path)
    if digest != ARCHIVE_SHA256:
        raise ValueError(f"{path.name} has sha256 {digest}, not {ARCHIVE_SHA256}")


def crop_and_square(img: Image.Image, margin: float = 0.05) -> Image.Image:
    """Crop ``img`` to its content plus ``margin`` and pad it with white to a square."""
    # A pixel is content when any channel, so its darkest channel, is at or below the threshold.
    darkest = functools.reduce(ImageChops.darker, img.split())
    mask = darkest.point(lambda value: 255 if value <= WHITE_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError("the image is white everywhere")
    left, top, right, bottom = box
    pad_x = min(int((right - left) * margin), left, img.width - right)
    pad_y = min(int((bottom - top) * margin), top, img.height - bottom)
    cropped = img.crop((left - pad_x, top - pad_y, right + pad_x, bottom + pad_y))
    side = max(cropped.size)
    square = Image.new("RGB", (side, side), (255, 255, 255))
    square.paste(cropped, ((side - cropped.width) // 2, (side - cropped.height) // 2))
    return square


def build(media_dir: Path, archive: Path | None = None) -> list[Path]:
    """Download, verify and crop the 80 images into ``media_dir``; return the written paths.

    ``archive`` skips the download: any copy of the archive with the right digest will do.
    The images are cropped and checked in a temporary folder before anything under
    ``media_dir`` is created or changed. Then each image replaces the file of its name in
    ``media_dir`` (created if missing), and the folder's other files are kept (``_replace``).
    Raises ``ValueError`` if the archive's digest is wrong, or if any cropped image's digest
    differs from ``media.sha256`` (the message names those images). On that or any other error,
    or an interruption such as Ctrl-C, ``media_dir`` is left as it was; a process killed while
    the folder is being swapped can leave the old folder in a hidden folder beside it.
    """
    expected = _expected_digests()
    media_dir = Path(media_dir)
    with tempfile.TemporaryDirectory() as tmp:
        if archive is None:
            archive = download(Path(tmp))
        verify(archive)
        staged = Path(tmp) / "images"
        staged.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for name in expected:
                with Image.open(io.BytesIO(zf.read(f"Clipart_JPG/{name}"))) as img:
                    square = crop_and_square(img)
                square.save(staged / name, "JPEG", quality=95)
        differing = [name for name, digest in expected.items()
                     if _sha256(staged / name) != digest]
        if differing:
            raise ValueError(f"cropped images differ from {_DIGESTS.name}: {', '.join(differing)}")
        _replace(media_dir, staged)
    return [media_dir / name for name in expected]


def _replace(media_dir: Path, staged: Path) -> None:
    """Put every file of ``staged`` into ``media_dir``, keeping its other files.

    A copy of ``media_dir`` with the staged files in place of their namesakes is made beside it
    and swapped in by two renames. If an error or an interruption such as Ctrl-C stops them,
    the old folder is put back; a killed process can leave it in the hidden folder beside
    ``media_dir``. A symbolic link is kept: the folder it points to is the one updated.
    """
    media_dir = media_dir.resolve()
    media_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=media_dir.parent,
                                     prefix=f".{media_dir.name}-") as swap:
        new, previous = Path(swap) / "new", Path(swap) / "previous"
        if media_dir.exists():
            shutil.copytree(media_dir, new, symlinks=True)
        else:
            new.mkdir()
        for path in staged.iterdir():
            (new / path.name).unlink(missing_ok=True)
            shutil.copyfile(path, new / path.name)
        try:
            if media_dir.exists():
                media_dir.rename(previous)
            new.rename(media_dir)
        except BaseException:
            if previous.exists() and not media_dir.exists():
                previous.rename(media_dir)
            raise


def _expected_digests() -> dict[str, str]:
    """The sha256 digest of each image participants saw, by file name."""
    digests = {}
    for line in _DIGESTS.read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        digests[Path(path).name] = digest
    return digests


def _sha256(path: Path) -> str:
    """The sha256 digest of the file at ``path``, in hex."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
