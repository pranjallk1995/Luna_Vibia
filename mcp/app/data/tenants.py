"""One PostgreSQL schema per person. Identical in every Luna app.

Each person's tables live in the schema ``u_<id>``. A connection's search path names
that schema for one transaction at a time, followed by ``public``, which holds only the
pgvector extension: no table is ever left there for a query to fall through to.
"""

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from psycopg import sql

from app.core import tenancy

logger = logging.getLogger(__name__)

# Serializes schema changes across connections; any fixed number works.
SCHEMA_LOCK = 7264519
ADOPTABLE_TABLES = """
    SELECT c.relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
"""
ADOPTABLE_FUNCTIONS = """
    SELECT p.oid::regprocedure::text AS signature FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
"""


def first_value(row: Any) -> Any:
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


def use_space(connection: Any, user_id: str) -> None:
    """Point this transaction, and only this transaction, at a person's schema."""
    connection.execute(
        "SELECT set_config('search_path', %s, true)", (f"{tenancy.space_name(user_id)}, public",)
    )


class TenantSchemas:
    """Create each person's schema the first time it is needed in this process."""

    def __init__(self, transaction: Callable[[], AbstractContextManager], create_tables: Callable[[Any], None]) -> None:
        self.transaction = transaction
        self.create_tables = create_tables
        # Fills a new person's defaults (presets, public URL); runs acting as that person.
        self.after_create: Callable[[], None] | None = None
        self._ready: set[str] = set()
        self._creating: set[str] = set()
        self._lock = threading.RLock()

    def adopt_public_tables(self) -> int:
        """Move data from before there were users into the owner's schema, all or nothing."""
        with self.transaction() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
            tables = [first_value(row) for row in connection.execute(ADOPTABLE_TABLES).fetchall()]
            if not tables:
                return 0
            owner = sql.Identifier(tenancy.space_name(tenancy.OWNER))
            connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(owner))
            for table in tables:
                connection.execute(
                    sql.SQL("ALTER TABLE public.{} SET SCHEMA {}").format(sql.Identifier(table), owner)
                )
            # regprocedure text is already quoted and schema-qualified as needed for ALTER FUNCTION.
            for row in connection.execute(ADOPTABLE_FUNCTIONS).fetchall():
                connection.execute(sql.SQL("ALTER FUNCTION {} SET SCHEMA {}").format(sql.SQL(first_value(row)), owner))
        logger.warning("Moved %d existing tables into the owner's schema.", len(tables))
        return len(tables)

    def ensure(self, user_id: str) -> None:
        if user_id in self._ready:
            return
        with self._lock:
            # The creator's own queries arrive here while it fills in the defaults.
            if user_id in self._ready or user_id in self._creating:
                return
            self._creating.add(user_id)
            try:
                with self.transaction() as connection:
                    connection.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
                    connection.execute(
                        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(tenancy.space_name(user_id)))
                    )
                    use_space(connection, user_id)
                    self.create_tables(connection)
                if self.after_create is not None:
                    with tenancy.acting_as(user_id):
                        self.after_create()
                self._ready.add(user_id)
            finally:
                self._creating.discard(user_id)

    def users(self) -> list[str]:
        """Everyone with a schema here, the owner first."""
        prefix = tenancy.SCHEMA_PREFIX
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT nspname FROM pg_namespace WHERE starts_with(nspname, %s) ORDER BY nspname", (prefix,)
            ).fetchall()
        users = [first_value(row)[len(prefix) :] for row in rows]
        return sorted(filter(tenancy.is_valid, users), key=lambda user_id: user_id != tenancy.OWNER)

    def user_with(self, query: str, params: tuple) -> str | None:
        """The first person whose schema has a row for ``query``: for public links, which name no user."""
        for user_id in self.users():
            with self.transaction() as connection:
                use_space(connection, user_id)
                if connection.execute(query, params).fetchone():
                    return user_id
        return None


def adopt_loose_files(root: Path) -> int:
    """Move vault files from before there were users into the owner's folder."""
    owner = root / tenancy.space_name(tenancy.OWNER)
    root.mkdir(parents=True, exist_ok=True)
    loose = [entry for entry in root.iterdir() if not (entry.is_dir() and entry.name.startswith(tenancy.SCHEMA_PREFIX))]
    if loose:
        owner.mkdir(exist_ok=True)
    for entry in loose:
        target = owner / entry.name
        if target.exists():
            raise RuntimeError(f"Cannot move {entry.name} into the owner's folder: it already exists there.")
        entry.rename(target)
    if loose:
        logger.warning("Moved %d existing files into the owner's folder.", len(loose))
    return len(loose)
