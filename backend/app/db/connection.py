"""Dual-Engine Relational Database Connection & Transaction Management (Phase D9.6).

Strictly preserves desktop architecture:
- Desktop mode (LIMO_SURFACE=desktop or unset): 100% local SQLite with WAL mode,
  foreign keys, and dictionary row access (sqlite3.Row).
- Web mode (LIMO_SURFACE=web): PostgreSQL via psycopg with dict_row factory,
  lexical dialect-safe parameter translation (? -> %s), and transaction management.
"""

from contextlib import contextmanager
from datetime import datetime
import logging
from pathlib import Path
import re
import sqlite3
from typing import Any, Generator, List, Optional, Tuple, Union

from ..config import settings

logger = logging.getLogger("limo.db.connection")

try:
    import psycopg
    from psycopg.rows import dict_row
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False


def adapt_sql_placeholders(sql: str) -> str:
    """Safely convert SQLite '?' parameter markers to PostgreSQL '%s' placeholders.

    Lexically skips single-quoted string literals ('...'), double-quoted identifiers ("..."),
    and SQL comments (-- ... and /* ... */) to prevent accidental corruption of literals.
    """
    out = []
    i = 0
    n = len(sql)
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        c = sql[i]

        # Handle line comments
        if in_line_comment:
            out.append(c)
            if c == "\n":
                in_line_comment = False
            i += 1
            continue

        # Handle block comments
        if in_block_comment:
            out.append(c)
            if c == "*" and i + 1 < n and sql[i + 1] == "/":
                out.append("/")
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # Handle single-quoted literals ('...')
        if in_single_quote:
            out.append(c)
            if c == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    # Escaped quote ''
                    out.append("'")
                    i += 2
                    continue
                else:
                    in_single_quote = False
            i += 1
            continue

        # Handle double-quoted identifiers ("...")
        if in_double_quote:
            out.append(c)
            if c == '"':
                if i + 1 < n and sql[i + 1] == '"':
                    out.append('"')
                    i += 2
                    continue
                else:
                    in_double_quote = False
            i += 1
            continue

        # Check comment starts
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            out.append("--")
            in_line_comment = True
            i += 2
            continue

        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            out.append("/*")
            in_block_comment = True
            i += 2
            continue

        # Check quote starts
        if c == "'":
            out.append(c)
            in_single_quote = True
            i += 1
            continue

        if c == '"':
            out.append(c)
            in_double_quote = True
            i += 1
            continue

        # Placeholder replacement outside literals
        if c == "?":
            out.append("%s")
            i += 1
            continue

        out.append(c)
        i += 1

    return "".join(out)


class LimoCursorWrapper:
    """Unified cursor wrapper guaranteeing dict-like row access and rowcount across engines."""

    def __init__(self, raw_cursor: Any, is_postgres: bool = False):
        self._raw_cursor = raw_cursor
        self.is_postgres = is_postgres

    @property
    def rowcount(self) -> int:
        return self._raw_cursor.rowcount

    def fetchone(self) -> Any:
        return self._raw_cursor.fetchone()

    def fetchall(self) -> List[Any]:
        return self._raw_cursor.fetchall()

    def __iter__(self):
        return iter(self._raw_cursor)


class LimoConnection:
    """Unified database connection wrapper supporting SQLite and PostgreSQL."""

    def __init__(self, raw_conn: Any, is_postgres: bool = False):
        self._conn = raw_conn
        self.is_postgres = is_postgres

    def execute(self, query: str, params: Union[Tuple, List] = ()) -> LimoCursorWrapper:
        """Execute a query with engine-appropriate placeholder translation."""
        if self.is_postgres:
            adapted_sql = adapt_sql_placeholders(query)
            cur = self._conn.execute(adapted_sql, tuple(params))
            return LimoCursorWrapper(cur, is_postgres=True)
        else:
            cur = self._conn.execute(query, tuple(params))
            return LimoCursorWrapper(cur, is_postgres=False)

    def executescript(self, script: str) -> None:
        """Execute multiple SQL statements sequentially."""
        if self.is_postgres:
            with self._conn.cursor() as cur:
                cur.execute(script)
        else:
            self._conn.executescript(script)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


@contextmanager
def get_connection(
    db_path: Optional[Union[str, Path]] = None,
    database_url: Optional[str] = None,
) -> Generator[LimoConnection, None, None]:
    """Provide a short-lived database connection with strict transactional safety.

    - If LIMO_SURFACE=web and DATABASE_URL is configured: opens PostgreSQL connection.
    - Otherwise (default desktop): opens local SQLite connection with WAL mode.
    """
    surface = settings.surface.lower() if hasattr(settings, "surface") else "desktop"
    pg_url = database_url or (settings.database_url if hasattr(settings, "database_url") else None)

    if surface == "web" and pg_url:
        if not HAS_PSYCOPG:
            raise RuntimeError(
                "psycopg is required for web deployment with PostgreSQL. Install psycopg[binary]."
            )
        raw_conn = psycopg.connect(pg_url, row_factory=dict_row)
        conn = LimoConnection(raw_conn, is_postgres=True)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        path = Path(db_path) if db_path else settings.db_path
        path.parent.mkdir(parents=True, exist_ok=True)

        raw_conn = sqlite3.connect(str(path), timeout=5.0)
        raw_conn.row_factory = sqlite3.Row

        raw_conn.execute("PRAGMA foreign_keys = ON;")
        raw_conn.execute("PRAGMA journal_mode = WAL;")
        raw_conn.execute("PRAGMA synchronous = NORMAL;")
        raw_conn.execute("PRAGMA busy_timeout = 5000;")

        conn = LimoConnection(raw_conn, is_postgres=False)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
