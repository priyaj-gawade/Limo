"""SQLite connection and transaction management.

Adheres strictly to short-lived per-operation connection lifecycle:
request/operation -> open connection -> transaction -> close connection.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional, Union
from ..config import settings


@contextmanager
def get_connection(db_path: Optional[Union[str, Path]] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a short-lived SQLite database connection with transactional safety.

    Enforces foreign keys, WAL journaling, and automatic commit/rollback.
    Closes the connection immediately upon context exit.
    """
    path = Path(db_path) if db_path else settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row

    # Enforce SQLite engine pragmas per operation
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
