import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_SQLITE_DB_PATH = "data/mpp_core.db"
_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _resolve_db_path(db_path: Optional[str] = None) -> Path:
    raw_path = db_path or os.getenv("MPP_SQLITE_DB_PATH", DEFAULT_SQLITE_DB_PATH)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def apply_schema(connection: sqlite3.Connection) -> None:
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema_sql)
    connection.commit()


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_first_run = not path.exists()

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    if is_first_run:
        apply_schema(connection)

    return connection
