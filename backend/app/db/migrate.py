from __future__ import annotations

from pathlib import Path

from backend.app.db.connection import get_connection
from backend.app.services.validation import ValidationError

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
MIGRATION_FILES = ("001_init.sql", "002_users.sql", "003_auth_sessions.sql")


def _split_statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                parts.append(stmt)
            buf = []
    trailing = "\n".join(buf).strip()
    if trailing:
        parts.append(trailing)
    return parts


def _ensure_clubing_constraints(cur) -> None:
    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'clubing'
          AND index_name = 'uq_clubing_club_id'
        """
    )
    if cur.fetchone()["c"] == 0:
        cur.execute(
            "UPDATE clubing SET club_id = CONCAT('CLUB-', s_no) "
            "WHERE club_id IS NULL OR club_id = ''"
        )
        cur.execute("CREATE UNIQUE INDEX uq_clubing_club_id ON clubing (club_id)")

    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'clubing'
          AND index_name = 'idx_clubing_department'
        """
    )
    if cur.fetchone()["c"] == 0:
        cur.execute("CREATE INDEX idx_clubing_department ON clubing (department)")


def _align_users_schema(cur) -> None:
    """Safe adjustments for an already-created users table."""
    cur.execute(
        """
        SELECT COUNT(*) AS c
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = 'users'
        """
    )
    if cur.fetchone()["c"] == 0:
        return
    cur.execute("ALTER TABLE users MODIFY username VARCHAR(100) NOT NULL")


def run_migrations() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for name in MIGRATION_FILES:
                sql_path = MIGRATIONS_DIR / name
                if not sql_path.is_file():
                    raise ValidationError(f"Migration file missing: {sql_path}")
                for stmt in _split_statements(sql_path.read_text(encoding="utf-8")):
                    cur.execute(stmt)
            _ensure_clubing_constraints(cur)
            _align_users_schema(cur)
        conn.commit()
    except ValidationError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise ValidationError(f"Database migration failed: {e}") from e
    finally:
        conn.close()
