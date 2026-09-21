"""Sandboxed filesystem storage service for Limo sources and artifacts.

Enforces strict boundary isolation under data/ (sources/, artifacts/, temp/),
prevents path traversal attacks, guarantees atomic file writes via fsync and rename,
and computes cryptographic SHA-256 digests.
"""

import hashlib
import logging
import os
from pathlib import Path
import re
from typing import Optional, Tuple, Union
import uuid

from ..config import settings
from ..exceptions import StorageError

logger = logging.getLogger("limo.storage")


class StorageService:
    """Manages secure sandboxed file operations for sources and generated artifacts."""

    def __init__(self, base_dir: Optional[Union[str, Path]] = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path(settings.data_dir).resolve()
        self.sources_dir = self.base_dir / "sources"
        self.artifacts_dir = self.base_dir / "artifacts"
        self.extractions_dir = self.base_dir / "extractions"
        self.temp_dir = self.base_dir / "temp"

        # Web surface cloud persistence (Supabase Storage)
        self._web_storage = None
        if settings.limo_surface.lower() == "web":
            try:
                from .web_storage import WebArtifactStorage
                self._web_storage = WebArtifactStorage(local_cache_dir=self.artifacts_dir)
            except Exception as exc:
                logger.warning("Failed to initialize WebArtifactStorage: %s", exc)

    def ensure_directories(self) -> None:
        """Create storage root and mandatory subdirectories safely."""
        for directory in (self.sources_dir, self.artifacts_dir, self.extractions_dir, self.temp_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def safe_resolve(self, storage_ref: str) -> Path:
        """Resolve a storage reference within the sandbox boundary.

        Raises StorageError if path traversal or escape outside sandbox is detected.
        """
        if not storage_ref or not isinstance(storage_ref, str):
            raise StorageError("Storage reference cannot be empty")

        # Reject explicit root / absolute path injections
        if storage_ref.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:", storage_ref):
            raise StorageError(f"Absolute or rooted storage reference rejected: '{storage_ref}'")

        # Strip relative path components and resolve
        resolved_path = (self.base_dir / storage_ref).resolve()

        # Strict boundary check
        if not self._is_within_boundary(resolved_path):
            raise StorageError(
                f"Path traversal detected: storage reference '{storage_ref}' resolves outside approved sandbox"
            )

        return resolved_path

    def _is_within_boundary(self, path: Path) -> bool:
        """Check if resolved path is strictly within base_dir."""
        try:
            return path.is_relative_to(self.base_dir)
        except AttributeError:
            # Fallback for Python versions without Path.is_relative_to
            try:
                path.relative_to(self.base_dir)
                return True
            except ValueError:
                return False

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Calculate standardized 64-character lowercase SHA-256 hexadecimal digest."""
        return hashlib.sha256(content).hexdigest().lower()

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Strip directory indicators and dangerous characters from filename."""
        clean_name = os.path.basename(filename).strip()
        # Keep alphanumeric, dots, dashes, underscores
        clean_name = re.sub(r"[^a-zA-Z0-9._-]", "_", clean_name)
        if not clean_name or clean_name in (".", ".."):
            clean_name = f"unnamed_{uuid.uuid4().hex[:8]}"
        return clean_name

    def _atomic_write(self, target_path: Path, content: bytes) -> Tuple[int, str]:
        """Perform verified atomic file write.

        Explicit flow:
        1. Calculate SHA-256 digest.
        2. Write bytes to temporary file in temp_dir.
        3. Flush and fsync to guarantee disk persistence.
        4. Close file descriptor.
        5. Atomically replace/rename temp file to target path.
        6. Verify existence and byte count.
        7. Return (size_bytes, sha256_hash).
        """
        self.ensure_directories()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        sha256_hash = self.compute_sha256(content)
        temp_filename = f"tmp_{uuid.uuid4().hex}.tmp"
        temp_path = self.temp_dir / temp_filename

        try:
            # Step 1-4: Write temp file, flush, fsync, close
            with open(temp_path, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Step 5: Atomic rename
            os.replace(temp_path, target_path)

            # Step 6: Verify
            if not target_path.exists():
                raise StorageError(f"Atomic file creation verification failed for {target_path}")

            actual_size = target_path.stat().st_size
            if actual_size != len(content):
                raise StorageError(
                    f"File size mismatch for {target_path}: expected {len(content)}, got {actual_size}"
                )

            return actual_size, sha256_hash

        except Exception as e:
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            if isinstance(e, StorageError):
                raise
            raise StorageError(f"Atomic file write failed for {target_path}: {e}") from e

    def save_source_file(self, source_id: str, filename: str, content: bytes) -> Tuple[str, int, str]:
        """Atomically persist an ingested source asset.

        Returns: (storage_ref, size_bytes, sha256_hash).
        """
        clean_name = self._sanitize_filename(filename)
        storage_ref = f"sources/{source_id}/{clean_name}"
        target_path = self.safe_resolve(storage_ref)

        size_bytes, sha256_hash = self._atomic_write(target_path, content)
        logger.info("Saved source file '%s' (%d bytes, sha256: %s)", storage_ref, size_bytes, sha256_hash[:8])
        return storage_ref, size_bytes, sha256_hash

    def save_artifact_file(self, artifact_id: str, filename: str, content: bytes) -> Tuple[str, int, str]:
        """Atomically persist a generated deliverable artifact.

        On web surface with Supabase Storage, persists durably to cloud storage and caches locally.
        On desktop, saves strictly to local sandboxed storage.

        Returns: (storage_ref, size_bytes, sha256_hash).
        """
        clean_name = self._sanitize_filename(filename)

        # Web surface Supabase Storage flow
        if self._web_storage and self._web_storage.is_configured:
            return self._web_storage.save_artifact(artifact_id, clean_name, content)

        # Local filesystem flow
        storage_ref = f"artifacts/{artifact_id}/{clean_name}"
        target_path = self.safe_resolve(storage_ref)

        size_bytes, sha256_hash = self._atomic_write(target_path, content)
        logger.info("Saved artifact file '%s' (%d bytes, sha256: %s)", storage_ref, size_bytes, sha256_hash[:8])
        return storage_ref, size_bytes, sha256_hash

    def save_extraction_file(self, source_id: str, content: bytes) -> str:
        """Atomically persist structured extraction JSON result."""
        storage_ref = f"extractions/{source_id}.json"
        target_path = self.safe_resolve(storage_ref)
        self._atomic_write(target_path, content)
        logger.info("Saved extraction result '%s'", storage_ref)
        return storage_ref

    def read_file(self, storage_ref: str) -> bytes:
        """Read binary contents from a sandboxed storage reference.

        On web surface, checks local cache first; if cold-started or restarted,
        recovers durable binary from Supabase Storage.
        """
        # If web storage is active and this is an artifact, try web storage recovery
        if self._web_storage and self._web_storage.is_configured and storage_ref.startswith("artifacts/"):
            try:
                return self._web_storage.read_artifact(storage_ref)
            except Exception as e:
                logger.debug("Web storage read failed, attempting local fallback: %s", e)

        path = self.safe_resolve(storage_ref)
        if not path.is_file():
            raise StorageError(f"Storage asset not found: '{storage_ref}'")
        return path.read_bytes()

    def delete_file(self, storage_ref: str) -> bool:
        """Safely delete an asset if it exists."""
        if self._web_storage and self._web_storage.is_configured and storage_ref.startswith("artifacts/"):
            self._web_storage.delete_artifact(storage_ref)

        try:
            path = self.safe_resolve(storage_ref)
            if path.is_file():
                path.unlink()
                return True
            return False
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to delete '{storage_ref}': {e}") from e

    def file_exists(self, storage_ref: str) -> bool:
        """Check if an asset exists in approved storage boundaries."""
        if self._web_storage and self._web_storage.is_configured and storage_ref.startswith("artifacts/"):
            if self._web_storage.exists(storage_ref):
                return True

        try:
            path = self.safe_resolve(storage_ref)
            return path.is_file()
        except StorageError:
            return False


# Global default storage service instance
storage_service = StorageService()
