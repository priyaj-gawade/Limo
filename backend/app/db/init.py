"""Database initialization and schema application runner (surface & dialect aware)."""

import logging
from pathlib import Path
from typing import Optional, Union
from .connection import get_connection

logger = logging.getLogger("limo.db.init")


def init_db(
    db_path: Optional[Union[str, Path]] = None,
    database_url: Optional[str] = None,
) -> None:
    """Initialize database and apply schema DDL idempotently for the configured engine."""
    with get_connection(db_path=db_path, database_url=database_url) as conn:
        if conn.is_postgres:
            schema_file = Path(__file__).parent / "schema_postgres.sql"
            if not schema_file.exists():
                raise FileNotFoundError(f"PostgreSQL schema definition file missing at {schema_file}")
            schema_sql = schema_file.read_text(encoding="utf-8")
            conn.executescript(schema_sql)
            logger.info("Initialized PostgreSQL database schema successfully.")
        else:
            schema_file = Path(__file__).parent / "schema.sql"
            if not schema_file.exists():
                raise FileNotFoundError(f"Schema definition file missing at {schema_file}")
            schema_sql = schema_file.read_text(encoding="utf-8")
            conn.executescript(schema_sql)

            # Ensure new columns exist on existing databases
            rows = conn.execute("PRAGMA table_info(jobs)").fetchall()
            job_cols = {row["name"] if (isinstance(row, dict) or hasattr(row, "keys")) else row[1] for row in rows}
            if "prompt" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN prompt TEXT")
            if "source_ids_json" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN source_ids_json TEXT NOT NULL DEFAULT '[]'")
            if "user_id" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN user_id TEXT")
            if "execution_id" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN execution_id TEXT")
            if "worker_id" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN worker_id TEXT")
            if "attempt_count" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "claimed_at" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN claimed_at TEXT")
            if "cancellation_requested" not in job_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN cancellation_requested INTEGER NOT NULL DEFAULT 0")

            proj_rows = conn.execute("PRAGMA table_info(projects)").fetchall()
            project_cols = {row["name"] if (isinstance(row, dict) or hasattr(row, "keys")) else row[1] for row in proj_rows}
            if "user_id" not in project_cols:
                conn.execute("ALTER TABLE projects ADD COLUMN user_id TEXT")

            logger.info("Initialized SQLite database schema successfully.")
