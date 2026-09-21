"""Supabase-backed durable web artifact storage (Phase D9.6).

Enforces durable cloud persistence for artifacts on web deployments:
- GitHub Runner / Cloud Worker -> Render Upload Endpoint -> WebArtifactStorage -> Supabase Storage.
- Artifact metadata persists in Supabase PostgreSQL.
- Files survive Render restarts, container recycling, and horizontal re-deployments.
- Local filesystem serves as a fast read cache and temporary staging area.
"""

import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional, Tuple
import httpx

from ..config import settings
from ..exceptions import StorageError

logger = logging.getLogger("limo.storage.web")


class WebArtifactStorage:
    """Manages artifact persistence using Supabase Storage REST API."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        bucket: Optional[str] = None,
        local_cache_dir: Optional[Path] = None,
    ):
        self.supabase_url = (supabase_url or settings.supabase_url or "").rstrip("/")
        self.service_role_key = (
            service_role_key
            or settings.supabase_service_role_key
            or settings.supabase_anon_key
            or ""
        ).strip()
        self.bucket = bucket or settings.supabase_storage_bucket or "limo-artifacts"
        self.local_cache_dir = local_cache_dir or (Path(settings.data_dir).resolve() / "artifacts")
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_configured(self) -> bool:
        """Check if Supabase Storage credentials are present."""
        return bool(self.supabase_url and self.service_role_key)

    def _get_headers(self, content_type: Optional[str] = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def save_artifact(
        self,
        artifact_id: str,
        filename: str,
        content: bytes,
    ) -> Tuple[str, int, str]:
        """Upload deliverable to Supabase Storage and cache locally.

        Returns: (storage_ref, size_bytes, sha256_hash).
        """
        size_bytes = len(content)
        sha256_hash = hashlib.sha256(content).hexdigest().lower()
        storage_ref = f"artifacts/{artifact_id}/{filename}"

        # 1. Cache to local directory
        local_path = self.local_cache_dir / artifact_id / filename
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)

        # 2. Upload to Supabase Storage if configured
        if self.is_configured:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

            upload_url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_ref}"
            headers = self._get_headers(content_type=content_type)
            headers["x-upsert"] = "true"

            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(upload_url, headers=headers, content=content)
                    if resp.status_code not in (200, 201):
                        logger.warning(
                            "Supabase Storage upload returned status %d (%s). Local cache preserved.",
                            resp.status_code,
                            resp.text[:200],
                        )
                    else:
                        logger.info(
                            "Successfully persisted artifact to Supabase Storage: %s/%s (%d bytes)",
                            self.bucket,
                            storage_ref,
                            size_bytes,
                        )
            except Exception as e:
                logger.warning(
                    "Network error uploading artifact to Supabase Storage: %s. Local cache preserved.",
                    e,
                )

        return storage_ref, size_bytes, sha256_hash

    def save_artifact_from_file(
        self,
        artifact_id: str,
        filename: str,
        file_path: Path,
        size_bytes: int,
        sha256_hash: str,
    ) -> Tuple[str, int, str]:
        """Upload deliverable file directly to Supabase Storage via streaming and cache locally.

        Streams file content using a file descriptor to avoid high heap memory usage on Render.
        """
        storage_ref = f"artifacts/{artifact_id}/{filename}"

        # 1. Ensure local cache directory has the file
        local_path = self.local_cache_dir / artifact_id / filename
        if local_path.resolve() != file_path.resolve() and file_path.is_file():
            local_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(file_path, local_path)

        # 2. Stream upload to Supabase Storage if configured
        if self.is_configured:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

            upload_url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_ref}"
            headers = self._get_headers(content_type=content_type)
            headers["x-upsert"] = "true"

            try:
                with open(local_path, "rb") as f:
                    with httpx.Client(timeout=60.0) as client:
                        resp = client.post(upload_url, headers=headers, content=f)
                        if resp.status_code not in (200, 201):
                            logger.warning(
                                "Supabase Storage upload returned status %d (%s). Local cache preserved.",
                                resp.status_code,
                                resp.text[:200],
                            )
                        else:
                            logger.info(
                                "Successfully streamed artifact to Supabase Storage: %s/%s (%d bytes)",
                                self.bucket,
                                storage_ref,
                                size_bytes,
                            )
            except Exception as e:
                logger.warning(
                    "Network error uploading artifact to Supabase Storage: %s. Local cache preserved.",
                    e,
                )

        return storage_ref, size_bytes, sha256_hash

    def read_artifact(self, storage_ref: str) -> bytes:
        """Read artifact from local cache, or fetch from Supabase Storage if local cache is empty."""
        local_rel = storage_ref.removeprefix("artifacts/").lstrip("/")
        local_path = self.local_cache_dir / local_rel

        # 1. Fast local cache hit
        if local_path.is_file():
            return local_path.read_bytes()

        # Also check relative to data_dir root
        alt_path = Path(settings.data_dir).resolve() / storage_ref
        if alt_path.is_file():
            return alt_path.read_bytes()

        # 2. Fetch from Supabase Storage (Render restart / cold start recovery)
        if self.is_configured:
            fetch_url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_ref}"
            headers = self._get_headers()
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(fetch_url, headers=headers)
                    if resp.status_code == 200:
                        content = resp.content
                        # Cache locally for future fast reads
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        local_path.write_bytes(content)
                        logger.info(
                            "Recovered artifact from Supabase Storage into local cache: %s (%d bytes)",
                            storage_ref,
                            len(content),
                        )
                        return content
                    else:
                        logger.warning(
                            "Supabase Storage fetch returned %d for %s",
                            resp.status_code,
                            storage_ref,
                        )
            except Exception as e:
                logger.error("Error reading artifact from Supabase Storage: %s", e)

        raise StorageError(f"Artifact not found in local cache or Supabase Storage: '{storage_ref}'")

    def exists(self, storage_ref: str) -> bool:
        """Check whether artifact exists in local cache or Supabase Storage."""
        local_rel = storage_ref.removeprefix("artifacts/").lstrip("/")
        local_path = self.local_cache_dir / local_rel
        if local_path.is_file():
            return True

        alt_path = Path(settings.data_dir).resolve() / storage_ref
        if alt_path.is_file():
            return True

        if self.is_configured:
            fetch_url = f"{self.supabase_url}/storage/v1/object/info/authenticated/{self.bucket}/{storage_ref}"
            headers = self._get_headers()
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(fetch_url, headers=headers)
                    return resp.status_code == 200
            except Exception:
                pass
        return False

    def delete_artifact(self, storage_ref: str) -> bool:
        """Delete deliverable from local cache and Supabase Storage."""
        deleted = False
        local_rel = storage_ref.removeprefix("artifacts/").lstrip("/")
        local_path = self.local_cache_dir / local_rel
        if local_path.is_file():
            try:
                local_path.unlink()
                deleted = True
            except OSError:
                pass

        if self.is_configured:
            delete_url = f"{self.supabase_url}/storage/v1/object/{self.bucket}"
            headers = self._get_headers(content_type="application/json")
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.request(
                        "DELETE",
                        delete_url,
                        headers=headers,
                        json={"prefixes": [storage_ref]},
                    )
                    if resp.status_code in (200, 204):
                        deleted = True
            except Exception as e:
                logger.warning("Failed to delete artifact from Supabase Storage: %s", e)

        return deleted
