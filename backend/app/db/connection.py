from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from dotenv import load_dotenv

from backend.app.services.validation import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "invoice_generation"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


def get_connection() -> Connection:
    try:
        return pymysql.connect(**db_config())
    except pymysql.Error as e:
        raise ValidationError(
            f"Could not connect to MySQL database "
            f"{db_config()['database']!r}: {e}"
        ) from e


@contextmanager
def db_cursor(*, commit: bool = False) -> Iterator[DictCursor]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
            if commit:
                conn.commit()
            else:
                conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def db_transaction() -> Iterator[tuple[Connection, DictCursor]]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield conn, cur
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
