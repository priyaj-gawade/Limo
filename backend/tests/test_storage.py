"""Tests for Phase D3.4: Sandboxed Filesystem Storage."""

import hashlib
import os
from pathlib import Path
import pytest

from app.exceptions import StorageError
from app.storage.service import StorageService


@pytest.fixture
def temp_storage(tmp_path: Path) -> StorageService:
    """Provide an isolated StorageService rooted in a temporary test directory."""
    service = StorageService(base_dir=tmp_path)
    service.ensure_directories()
    return service


def test_storage_directories_creation(temp_storage: StorageService) -> None:
    """Verify that storage root, sources, artifacts, and temp subdirectories are created."""
    assert temp_storage.sources_dir.is_dir()
    assert temp_storage.artifacts_dir.is_dir()
    assert temp_storage.temp_dir.is_dir()


def test_atomic_save_and_read_source_file(temp_storage: StorageService) -> None:
    """Verify atomic write of a source file, hash calculation, and exact byte read."""
    payload = b"Hello, Limo Ingestion Engine! Content of test source document."
    expected_hash = hashlib.sha256(payload).hexdigest().lower()

    storage_ref, size_bytes, sha256_hash = temp_storage.save_source_file(
        source_id="src_1001",
        filename="report.pdf",
        content=payload
    )

    assert storage_ref == "sources/src_1001/report.pdf"
    assert size_bytes == len(payload)
    assert sha256_hash == expected_hash

    # Verify physical file existence
    assert temp_storage.file_exists(storage_ref)
    read_back = temp_storage.read_file(storage_ref)
    assert read_back == payload

    # Verify temp directory is clean (temp files removed after atomic rename)
    temp_files = list(temp_storage.temp_dir.iterdir())
    assert len(temp_files) == 0


def test_atomic_save_and_read_artifact_file(temp_storage: StorageService) -> None:
    """Verify atomic write of a generated artifact deliverable."""
    payload = b"PK\x03\x04...binary docx/pptx presentation stream..."
    expected_hash = hashlib.sha256(payload).hexdigest().lower()

    storage_ref, size_bytes, sha256_hash = temp_storage.save_artifact_file(
        artifact_id="art_999",
        filename="deliverable.pptx",
        content=payload
    )

    assert storage_ref == "artifacts/art_999/deliverable.pptx"
    assert size_bytes == len(payload)
    assert sha256_hash == expected_hash

    assert temp_storage.file_exists(storage_ref)
    assert temp_storage.read_file(storage_ref) == payload


def test_compute_sha256_helper(temp_storage: StorageService) -> None:
    """Verify compute_sha256 standalone helper returns accurate lowercase digests."""
    data = b"Arbitrary test string for hashing verification"
    expected = hashlib.sha256(data).hexdigest().lower()
    assert temp_storage.compute_sha256(data) == expected


def test_path_traversal_rejections(temp_storage: StorageService) -> None:
    """Verify that path traversal attempts raise StorageError."""
    malicious_refs = [
        "../../etc/passwd",
        r"..\..\boot.ini",
        "sources/../../secret.txt",
        "artifacts/art_1/../../../windows/system32/cmd.exe",
        "/absolute/root/file.txt",
        r"C:\Windows\System32\notepad.exe",
        "D:/foreign_drive.txt",
    ]

    for bad_ref in malicious_refs:
        with pytest.raises(StorageError):
            temp_storage.safe_resolve(bad_ref)


def test_delete_file_operations(temp_storage: StorageService) -> None:
    """Verify safe file deletion behavior."""
    payload = b"Deletable temporary content"
    storage_ref, _, _ = temp_storage.save_source_file("src_del", "trash.txt", payload)

    assert temp_storage.file_exists(storage_ref)
    assert temp_storage.delete_file(storage_ref) is True
    assert not temp_storage.file_exists(storage_ref)

    # Subsequent deletion returns False cleanly
    assert temp_storage.delete_file(storage_ref) is False


def test_read_non_existent_file_raises_storage_error(temp_storage: StorageService) -> None:
    """Verify reading a non-existent storage ref raises StorageError."""
    with pytest.raises(StorageError):
        temp_storage.read_file("sources/non_existent/missing.docx")


def test_atomic_write_rollback_cleans_temp_and_leaves_no_partial_file(temp_storage: StorageService, monkeypatch) -> None:
    """Verify atomic write failure cleans up temp files and leaves zero corrupt target files."""
    import os

    def failing_replace(src, dst):
        raise OSError("Simulated atomic replace failure")

    monkeypatch.setattr(os, "replace", failing_replace)

    target_ref = "sources/src_failed/payload.bin"
    with pytest.raises(StorageError) as exc_info:
        temp_storage.save_source_file("src_failed", "payload.bin", b"Test payload bytes")

    assert "Atomic file write failed" in str(exc_info.value)
    # Target file must NOT exist
    assert not temp_storage.file_exists(target_ref)
    # Temp directory must be clean (zero leftover temp files)
    temp_dir = temp_storage.base_dir / "temp"
    assert list(temp_dir.glob("*")) == []
