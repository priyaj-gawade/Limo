"""Architectural compliance tests for Phase D3.11: Strict Layer Separation.

Verifies:
FastAPI Router
      ↓
Service
      ↓
Repository / Storage

Rules:
- Routes handle HTTP concerns only.
- Routes MUST NOT import sqlite3, connection factories, or repositories directly.
- All database and storage operations must flow through services.
"""

import ast
from pathlib import Path
import pytest


def test_router_layer_does_not_import_db_or_repositories() -> None:
    """Audit all api/v1 route files to ensure zero direct database or repository coupling."""
    api_dir = Path(__file__).parent.parent / "app" / "api" / "v1"
    assert api_dir.exists() and api_dir.is_dir()

    forbidden_modules = {"sqlite3", "app.db", "db.connection", "repositories"}
    forbidden_symbols = {
        "get_connection",
        "ProjectRepository",
        "SourceRepository",
        "ChatRepository",
        "JobRepository",
        "ArtifactRepository",
    }

    violations = []

    for py_file in api_dir.glob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(f) for f in forbidden_modules):
                        violations.append(f"{py_file.name}: Direct import of forbidden module '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "db" in module or "repositories" in module or module == "sqlite3":
                    violations.append(f"{py_file.name}: Forbidden import from module '{module}'")
                for alias in node.names:
                    if alias.name in forbidden_symbols:
                        violations.append(f"{py_file.name}: Forbidden direct import of repository symbol '{alias.name}'")

    assert not violations, "Architectural boundary violation detected in route handlers:\n" + "\n".join(violations)
