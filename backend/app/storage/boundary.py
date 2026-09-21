"""Storage boundary and worker reference resolution (Phase D9.6).

Defines:
1. Canonical worker://<artifact_id> reference validation and parsing.
2. Provider-neutral storage distinction between local desktop storage,
   worker heavy artifacts, and remote web storage.
"""

import re
from typing import Optional

WORKER_PREFIX = "worker://"
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


def is_worker_artifact_ref(ref: Optional[str]) -> bool:
    """Check if the given storage reference refers to a heavy Turbo Worker deliverable."""
    if not ref:
        return False
    return ref.startswith(WORKER_PREFIX)


def parse_worker_artifact_id(ref: str) -> str:
    """Extract and validate the artifact ID from a worker://<artifact_id> reference."""
    if not is_worker_artifact_ref(ref):
        raise ValueError(f"Reference '{ref}' is not a valid worker artifact reference")

    artifact_id = ref[len(WORKER_PREFIX):].strip()
    if not SAFE_ID_REGEX.match(artifact_id):
        raise ValueError(f"Worker artifact ID '{artifact_id}' contains invalid characters")

    return artifact_id
