"""Database initialization and schema application runner."""

import logging
from pathlib import Path
from typing import Optional, Union
from .connection import get_connection

logger = logging.getLogger("limo.db.init")


def init_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """Initialize SQLite database and apply schema DDL idempotently."""
    schema_file = Path(__file__).parent / "schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema definition file missing at {schema_file}")

    schema_sql = schema_file.read_text(encoding="utf-8")

    with get_connection(db_path) as conn:
        conn.executescript(schema_sql)
        # Ensure new columns exist on existing databases
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "prompt" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN prompt TEXT")
        if "source_ids_json" not in existing_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN source_ids_json TEXT NOT NULL DEFAULT '[]'")

    logger.info("Initialized SQLite database schema successfully.")

