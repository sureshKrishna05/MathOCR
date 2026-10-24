"""Tests for model storage, manifest verification, and download integrity."""

from pathlib import Path
import pytest

from backend import model_store
from backend.model_store import (
    PIX2TEX_MANIFEST,
    RAPID_LATEX_MANIFEST,
    TESSERACT_MANIFEST,
    check_disk_space,
    compute_sha256,
    verify_file_integrity,
    _download,
    required_models_status,
)


def test_manifest_entries_have_valid_structure() -> None:
    for manifest in (PIX2TEX_MANIFEST, RAPID_LATEX_MANIFEST, TESSERACT_MANIFEST):
        for name, entry in manifest.items():
            assert entry.name == name
            assert entry.url.startswith("https://")
            assert len(entry.sha256) == 64  # valid sha256 hex string
            assert entry.size > 0
            assert entry.license in ("MIT", "Apache-2.0")
            assert entry.role in ("required", "optional")


def test_verify_file_integrity_valid(tmp_path: Path) -> None:
    sample_file = tmp_path / "sample.bin"
    sample_data = b"Hello MathOCR Verification"
    sample_file.write_bytes(sample_data)

    expected_sha = compute_sha256(sample_file)
    assert verify_file_integrity(sample_file, expected_sha256=expected_sha, expected_size=len(sample_data))


def test_verify_file_integrity_mismatch(tmp_path: Path) -> None:
    sample_file = tmp_path / "sample.bin"
    sample_file.write_bytes(b"actual data")

    bad_sha = "0" * 64
    assert not verify_file_integrity(sample_file, expected_sha256=bad_sha)
    assert not verify_file_integrity(sample_file, expected_size=999999)


def test_check_disk_space_raises_on_insufficient_space(monkeypatch, tmp_path: Path) -> None:
    class MockUsage:
        free = 10 * 1024 * 1024  # only 10 MB free
        total = 100 * 1024 * 1024
        used = 90 * 1024 * 1024

    monkeypatch.setattr(model_store.shutil, "disk_usage", lambda path: MockUsage())
    with pytest.raises(OSError, match="Insufficient disk space"):
        check_disk_space(500 * 1024 * 1024, tmp_path)


def test_download_rejects_checksum_mismatch(monkeypatch, tmp_path: Path) -> None:
    class MockResponse:
        def __init__(self, data: bytes):
            self._data = data
            self._pos = 0

        def read(self, amt: int):
            chunk = self._data[self._pos : self._pos + amt]
            self._pos += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    # Provide data that does NOT match expected_sha
    mock_data = b"corrupted data from network"
    monkeypatch.setattr(
        model_store.urllib.request,
        "urlopen",
        lambda req, timeout=120: MockResponse(mock_data),
    )

    dest = tmp_path / "model.bin"
    bad_sha = "a" * 64

    with pytest.raises(OSError, match="Failed to download"):
        _download(
            "https://example.com/model.bin",
            dest,
            expected_sha256=bad_sha,
            max_retries=1,
        )

    # Destination should not exist, partial must be cleaned up
    assert not dest.exists()
    assert not (tmp_path / "model.bin.part").exists()


def test_required_models_status_reports_correctly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MATHOCR_MODEL_DIR", str(tmp_path))
    # Initially empty
    status = required_models_status()
    assert status["pix2tex"] is False
    assert status["rapid-latex"] is False
    assert status["tesseract"] is False
    assert status["pix2text"] is False
