"""Model storage management for MathOCR.

Authored by Bouronikos Christos <chrisbouronikos@gmail.com>.
Donations are welcome at https://paypal.me/christosbouronikos.

Every recognition model MathOCR downloads is kept below one per-user cache
folder. That single root makes the storage panel in the interface truthful:
sizes can be measured, and deleting an engine's folder really frees the space.

The folder is chosen per platform and can be overridden with the
``MATHOCR_MODEL_DIR`` environment variable:

- macOS:   ~/Library/Application Support/MathOCR/models
- Windows: %LOCALAPPDATA%/MathOCR/models
- Linux:   $XDG_CACHE_HOME/mathocr/models (default ~/.cache/mathocr/models)

pix2tex and RapidLaTeXOCR would normally download weights *into their own
package directory*, which is read-only inside an installed desktop app (for
example under Program Files). MathOCR therefore downloads those files itself,
into this cache, and hands the engines explicit paths.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("mathocr.model_store")

USER_AGENT = "MathOCR/1.0 (+https://github.com/ChristosBouronikos/MathOCR)"


@dataclass(frozen=True, slots=True)
class ModelFileManifest:
    """Versioned metadata for one model or language asset."""

    name: str
    url: str
    sha256: str
    size: int
    license: str
    role: str = "required"  # "required" or "optional"


# Pinned upstream model files with verified SHA-256 hashes and file sizes.
PIX2TEX_MANIFEST: dict[str, ModelFileManifest] = {
    "weights.pth": ModelFileManifest(
        name="weights.pth",
        url="https://github.com/lukas-blecher/LaTeX-OCR/releases/download/v0.0.1/weights.pth",
        sha256="a63d9141c53d266cb682fb5a8bd83bd5cbe283145e0e78ebdc0f895195a1dfaa",
        size=102113875,
        license="MIT",
        role="required",
    ),
    "image_resizer.pth": ModelFileManifest(
        name="image_resizer.pth",
        url="https://github.com/lukas-blecher/LaTeX-OCR/releases/download/v0.0.1/image_resizer.pth",
        sha256="1c3820659985ad142b526490bb25c23d977176ac2073591b3bddada692718458",
        size=19441973,
        license="MIT",
        role="required",
    ),
}

RAPID_LATEX_MANIFEST: dict[str, ModelFileManifest] = {
    "encoder.onnx": ModelFileManifest(
        name="encoder.onnx",
        url="https://github.com/RapidAI/RapidLatexOCR/releases/download/v0.0.0/encoder.onnx",
        sha256="01bf5dc25539ca0cd5b1bd29296ea495977a6ba5f629dc4178277809d26e5e7d",
        size=89008136,
        license="Apache-2.0",
        role="required",
    ),
    "decoder.onnx": ModelFileManifest(
        name="decoder.onnx",
        url="https://github.com/RapidAI/RapidLatexOCR/releases/download/v0.0.0/decoder.onnx",
        sha256="bd695497bf1b22279b7626f5916c79226e1e244c84355f8da7edfd2d921d0072",
        size=50952726,
        license="Apache-2.0",
        role="required",
    ),
    "image_resizer.onnx": ModelFileManifest(
        name="image_resizer.onnx",
        url="https://github.com/RapidAI/RapidLatexOCR/releases/download/v0.0.0/image_resizer.onnx",
        sha256="e0b075c39700f64d50400f39c8fc186bbb3b5d84d31864008313f376603aca9d",
        size=38967751,
        license="Apache-2.0",
        role="required",
    ),
    "tokenizer.json": ModelFileManifest(
        name="tokenizer.json",
        url="https://github.com/RapidAI/RapidLatexOCR/releases/download/v0.0.0/tokenizer.json",
        sha256="1dc27b18d6a518d0d5ff3f4bb7bd98521fe80ad39e5b2a246d4109f1bb9d5019",
        size=24174,
        license="Apache-2.0",
        role="required",
    ),
}

TESSERACT_BASE = "https://github.com/tesseract-ocr/tessdata_fast/raw/main"
TESSERACT_LANGS = ("ell", "eng")
TESSERACT_MANIFEST: dict[str, ModelFileManifest] = {
    "ell.traineddata": ModelFileManifest(
        name="ell.traineddata",
        url=f"{TESSERACT_BASE}/ell.traineddata",
        sha256="4fba8a0b461038d51f1c20d043d4f2ac38c4e778f1b90830847f7bd8fa3ba726",
        size=1419514,
        license="Apache-2.0",
        role="required",
    ),
    "eng.traineddata": ModelFileManifest(
        name="eng.traineddata",
        url=f"{TESSERACT_BASE}/eng.traineddata",
        sha256="7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
        size=4113088,
        license="Apache-2.0",
        role="required",
    ),
}

# Backward compatibility mappings
PIX2TEX_FILES: dict[str, str] = {name: entry.url for name, entry in PIX2TEX_MANIFEST.items()}
RAPID_LATEX_FILES: dict[str, str] = {name: entry.url for name, entry in RAPID_LATEX_MANIFEST.items()}


def default_cache_root() -> Path:
    """Return the per-platform folder that holds every downloaded model."""
    override = os.getenv("MATHOCR_MODEL_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MathOCR" / "models"
    if sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / "MathOCR" / "models"
    xdg = os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(xdg) / "mathocr" / "models"


def configure_model_environment() -> Path:
    """Point every engine's own cache mechanism below the MathOCR root.

    Must run before any engine module is imported. Explicit user-provided
    values for the underlying variables are respected.
    """
    root = default_cache_root()
    os.environ.setdefault("PIX2TEXT_HOME", str(root / "pix2text"))
    os.environ.setdefault("CNSTD_HOME", str(root / "cnstd"))
    os.environ.setdefault("CNOCR_HOME", str(root / "cnocr"))
    # Nougat (optional) reads its checkpoint from this directory when present.
    os.environ.setdefault("NOUGAT_CHECKPOINT", str(root / "nougat"))
    return root


def tesseract_data_dir() -> Path:
    """Return the tessdata directory that holds MathOCR's language files."""
    return default_cache_root() / "tesseract" / "tessdata"


def compute_sha256(path: Path) -> str:
    """Calculate the SHA-256 checksum of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(256 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_file_integrity(
    path: Path, expected_sha256: str | None = None, expected_size: int | None = None
) -> bool:
    """Check that a file exists, is non-empty, and matches expected size and hash."""
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size == 0:
        return False
    if expected_size is not None and size != expected_size:
        return False
    if expected_sha256 is not None:
        return compute_sha256(path) == expected_sha256
    return True


def check_disk_space(required_bytes: int, target_dir: Path | None = None) -> None:
    """Check that sufficient disk space is available before initiating download."""
    check_path = target_dir or default_cache_root()
    check_path.mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(check_path)
        if usage.free < required_bytes:
            free_mb = usage.free // (1024 * 1024)
            req_mb = required_bytes // (1024 * 1024)
            raise OSError(
                f"Insufficient disk space in {check_path}. "
                f"Available: {free_mb} MB, Required: {req_mb} MB."
            )
    except OSError:
        raise
    except Exception as exc:
        logger.debug("disk_usage check skipped for %s: %s", check_path, exc)


def _download(
    url: str,
    destination: Path,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> None:
    """Stream one file to disk atomically with retry and SHA-256 verification."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            partial.unlink(missing_ok=True)
            hasher = hashlib.sha256() if expected_sha256 else None
            downloaded = 0
            with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as sink:
                while chunk := response.read(256 * 1024):
                    sink.write(chunk)
                    if hasher:
                        hasher.update(chunk)
                    downloaded += len(chunk)

            if downloaded == 0:
                raise OSError(f"Downloaded file is empty: {url}")
            if expected_size is not None and downloaded != expected_size:
                raise OSError(
                    f"Size mismatch for {destination.name}: expected {expected_size} bytes, got {downloaded} bytes."
                )
            if hasher and hasher.hexdigest() != expected_sha256:
                raise ValueError(
                    f"Checksum mismatch for {destination.name}: expected {expected_sha256}, got {hasher.hexdigest()}."
                )

            partial.replace(destination)
            return
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)

    raise OSError(f"Failed to download {url} after {max_retries} attempts: {last_error}") from last_error


def _ensure_files(
    directory: Path,
    files: dict[str, str] | dict[str, ModelFileManifest],
    strict_verify: bool = False,
) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for name, item in files.items():
        target = directory / name
        url = item.url if isinstance(item, ModelFileManifest) else item
        expected_sha256 = item.sha256 if isinstance(item, ModelFileManifest) else None
        expected_size = item.size if isinstance(item, ModelFileManifest) else None

        needs_download = False
        if not target.is_file() or target.stat().st_size == 0:
            needs_download = True
        elif strict_verify and expected_sha256:
            if not verify_file_integrity(target, expected_sha256=expected_sha256, expected_size=expected_size):
                needs_download = True

        if needs_download:
            if expected_size:
                check_disk_space(expected_size, directory)
            _download(url, target, expected_sha256=expected_sha256, expected_size=expected_size)
        resolved[name] = target
    return resolved


def ensure_pix2tex_weights() -> dict[str, Path]:
    """Download pix2tex checkpoint files into the MathOCR cache if missing."""
    return _ensure_files(default_cache_root() / "pix2tex", PIX2TEX_MANIFEST)


def ensure_rapid_latex_weights() -> dict[str, Path]:
    """Download RapidLaTeXOCR ONNX files into the MathOCR cache if missing."""
    return _ensure_files(default_cache_root() / "rapid-latex-ocr", RAPID_LATEX_MANIFEST)


def ensure_pix2text_models() -> list[Path]:
    """Download the Pix2Text detector and recognizer weights if missing.

    Reuses pix2text's own downloader so file layout stays exactly what the
    library expects at load time. Requires the pix2text package.
    """
    from pix2text.consts import AVAILABLE_MODELS, MODEL_VERSION
    from pix2text.utils import data_dir, prepare_model_files

    check_disk_space(200 * 1024 * 1024, Path(data_dir()))

    prepared: list[Path] = []
    for model_name in ("mfd-1.5", "mfr-1.5"):
        model_info = AVAILABLE_MODELS.get_info(model_name, "onnx")
        model_dir = Path(data_dir()) / MODEL_VERSION / model_info["local_model_id"]
        if not (model_dir.is_dir() and any(model_dir.rglob("*.onnx"))):
            prepare_model_files(data_dir(), model_info)
        prepared.append(model_dir)
    return prepared


def ensure_tesseract_langs() -> Path:
    """Download the Greek and English tessdata files if missing.

    Returns the tessdata directory to pass to Tesseract as ``--tessdata-dir``.
    """
    directory = tesseract_data_dir()
    _ensure_files(directory, TESSERACT_MANIFEST)
    return directory


def ensure_nougat_model() -> Path:
    """Download the optional Nougat checkpoint into the MathOCR store.

    Requires the optional ``nougat-ocr`` package. Nougat weights are licensed
    CC-BY-NC (non-commercial), which is why they are never bundled and are
    downloaded only when the user explicitly enables the engine.
    """
    from nougat.utils.checkpoint import get_checkpoint

    target = default_cache_root() / "nougat"
    target.mkdir(parents=True, exist_ok=True)
    check_disk_space(1400 * 1024 * 1024, target)
    # model_tag "0.1.0-small" is the CPU-friendly checkpoint.
    return Path(get_checkpoint(target, model_tag="0.1.0-small", download=True))


def required_models_status() -> dict[str, bool]:
    """Check whether each required model is present on disk and non-empty."""
    root = default_cache_root()
    status = {
        "pix2tex": all(
            (root / "pix2tex" / name).is_file() and (root / "pix2tex" / name).stat().st_size > 0
            for name in PIX2TEX_MANIFEST
        ),
        "rapid-latex": all(
            (root / "rapid-latex-ocr" / name).is_file()
            and (root / "rapid-latex-ocr" / name).stat().st_size > 0
            for name in RAPID_LATEX_MANIFEST
        ),
        "tesseract": all(
            (tesseract_data_dir() / name).is_file()
            and (tesseract_data_dir() / name).stat().st_size > 0
            for name in TESSERACT_MANIFEST
        ),
    }
    p2t_dir = root / "pix2text"
    status["pix2text"] = p2t_dir.is_dir() and any(p2t_dir.rglob("*.onnx"))
    return status


def all_required_models_ready() -> bool:
    """Return True if all required OCR models are installed and ready for offline use."""
    return all(required_models_status().values())


def directory_size(path: Path) -> int:
    """Total bytes of all files below ``path``; 0 when it does not exist."""
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


@dataclass(slots=True)
class StoreEntry:
    """One deletable model folder shown in the interface's storage panel."""

    engine: str
    path: Path
    bytes: int = 0
    legacy: bool = False

    def measure(self) -> StoreEntry:
        self.bytes = directory_size(self.path)
        return self


def store_entries() -> list[StoreEntry]:
    """Enumerate every folder MathOCR may occupy, including legacy locations.

    The legacy entries cover caches created by earlier MathOCR versions (or by
    using the libraries directly) in their default home-directory locations,
    so "delete everything" genuinely returns the disk space.
    """
    root = default_cache_root()
    entries = [
        StoreEntry("pix2text", Path(os.getenv("PIX2TEXT_HOME", str(root / "pix2text")))),
        StoreEntry("pix2tex", root / "pix2tex"),
        StoreEntry("rapid-latex", root / "rapid-latex-ocr"),
        StoreEntry("tesseract", root / "tesseract"),
        StoreEntry("nougat", Path(os.getenv("NOUGAT_CHECKPOINT", str(root / "nougat")))),
    ]

    legacy_candidates = {
        "pix2text": Path.home() / ".pix2text",
        "pix2tex": None,
        "rapid-latex": None,
    }
    if sys.platform == "win32" and os.getenv("APPDATA"):
        legacy_candidates["pix2text"] = Path(os.environ["APPDATA"]) / "pix2text"
    legacy_pix2text = legacy_candidates["pix2text"]
    already_listed = {entry.path.resolve() for entry in entries if entry.path.exists()}
    if (
        legacy_pix2text is not None
        and legacy_pix2text.exists()
        and legacy_pix2text.resolve() not in already_listed
    ):
        entries.append(StoreEntry("pix2text", legacy_pix2text, legacy=True))

    return [entry.measure() for entry in entries]


@dataclass(slots=True)
class DeletionReport:
    """Outcome of a storage cleanup request."""

    freed_bytes: int = 0
    deleted_paths: list[str] = field(default_factory=list)
    failed_paths: list[str] = field(default_factory=list)


def delete_engine_storage(engine: str | None = None) -> DeletionReport:
    """Delete downloaded model files for one engine, or all when ``None``."""
    report = DeletionReport()
    for entry in store_entries():
        if engine is not None and entry.engine != engine:
            continue
        if not entry.path.exists():
            continue
        size = entry.bytes
        try:
            shutil.rmtree(entry.path)
            report.freed_bytes += size
            report.deleted_paths.append(str(entry.path))
        except OSError:
            # Typically Windows refusing to remove files that are memory-mapped
            # by a loaded model. The caller unloads engines first, but a still
            # undeletable folder is reported instead of raising.
            report.failed_paths.append(str(entry.path))
    return report
