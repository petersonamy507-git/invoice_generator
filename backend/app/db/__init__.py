"""Database package for invoice_generation MySQL persistence."""

from backend.app.db.migrate import run_migrations

__all__ = ["run_migrations"]
