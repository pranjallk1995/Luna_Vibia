"""PostgreSQL persistence for Luna Vibia, one repository per aggregate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import psycopg

from app.data.database import Database
from app.core.models import TrackRecord

Row = dict[str, Any]

PUBLIC_TRACK_PATH = "/api/public/tracks/"


def search_vector_sql(name: str, caption: str, tags: str, credits: str = "concat_ws(' ', title, artist)") -> str:
    """Build the weighted full-text vector over filename, caption, title and artist, and tags."""
    return (
        f"setweight(to_tsvector('english', regexp_replace({name}, '[._-]+', ' ', 'g')), 'A') || "
        f"setweight(to_tsvector('english', {caption}), 'A') || "
        f"setweight(to_tsvector('english', coalesce({credits}, '')), 'A') || "
        f"setweight(to_tsvector('english', {tags}), 'B')"
    )


def vector_literal(values: list[float]) -> str | None:
    """pgvector's text form of an embedding, or None when there is none."""
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]" if values else None


def public_url_sql(base_url_parameter: str) -> str:
    """Build a stable public URL from the configured base and immutable track ID."""
    return f"{base_url_parameter} || '{PUBLIC_TRACK_PATH}' || track_id::text"


class Repository:
    """Shared query helpers that serialize rows into JSON-friendly dicts."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def serialize(row: Row | None) -> Row | None:
        if row is None:
            return None
        return {
            key: (
                value.isoformat()
                if hasattr(value, "isoformat")
                else str(value) if isinstance(value, UUID) else value
            )
            for key, value in row.items()
        }

    def fetch_one(self, sql: str, params: Any = ()) -> Row | None:
        with self.database.connect() as connection:
            return self.serialize(connection.execute(sql, params).fetchone())

    def fetch_all(self, sql: str, params: Any = ()) -> list[Row]:
        with self.database.connect() as connection:
            return [self.serialize(row) for row in connection.execute(sql, params).fetchall()]


class TrackRepository(Repository):
    """Track metadata, visibility, favorites, and the full-text search index."""

    COLUMNS = (
        "name, size_bytes, content_sha256, caption, tags, analysis_model, "
        "audio_format, duration_seconds, sample_rate, channels, bitrate, title, artist, notes, "
        "tempo_bpm, musical_key, energy, cover_url, "
        "updated_at, hidden, favorite, public_url, track_id"
    )
    # Written from a TrackRecord's facts; cover_url is kept across re-analysis.
    FACT_COLUMNS = (
        "audio_format", "duration_seconds", "sample_rate", "channels", "bitrate", "title",
        "artist", "notes", "tempo_bpm", "musical_key", "energy",
    )

    def upsert(self, record: TrackRecord, public_base_url: str) -> Row:
        """Insert or replace metadata and assign its stable public URL."""
        vector = search_vector_sql(
            "%(name)s", "%(caption)s", "array_to_string(%(tags)s::text[], ' ')",
            "concat_ws(' ', %(title)s::text, %(artist)s::text)",
        )
        values = {
            **{key: value for key, value in asdict(record).items() if key not in ("facts", "embedding")},
            **asdict(record.facts),
            "embedding": vector_literal(record.embedding),
        }
        facts = ", ".join(self.FACT_COLUMNS)
        placeholders = ", ".join(f"%({column})s" for column in self.FACT_COLUMNS)
        updates = ",\n                        ".join(f"{column} = EXCLUDED.{column}" for column in self.FACT_COLUMNS)
        with self.database.connect() as connection:
            connection.execute(
                f"""INSERT INTO track_metadata
                       (name, size_bytes, content_sha256, caption, tags,
                        analysis_model, {facts}, embedding, search_vector)
                    VALUES (%(name)s, %(size_bytes)s, %(content_sha256)s,
                            %(caption)s, %(tags)s, %(analysis_model)s, {placeholders},
                            %(embedding)s::vector, {vector})
                    ON CONFLICT (name) DO UPDATE SET
                        size_bytes = EXCLUDED.size_bytes,
                        content_sha256 = EXCLUDED.content_sha256,
                        caption = EXCLUDED.caption,
                        tags = EXCLUDED.tags,
                        analysis_model = EXCLUDED.analysis_model,
                        {updates},
                        embedding = EXCLUDED.embedding,
                        search_vector = EXCLUDED.search_vector,
                        updated_at = now()""",
                values,
            )
            row = connection.execute(
                f"""UPDATE track_metadata SET public_url = {public_url_sql('%s')}
                    WHERE name = %s RETURNING {self.COLUMNS}""",
                (public_base_url, record.name),
            ).fetchone()
        return self.serialize(row)

    def get(self, name: str, hidden: bool | None = False) -> Row | None:
        """Return one record, restricted to a collection unless ``hidden`` is None."""
        return self.fetch_one(
            f"""SELECT {self.COLUMNS} FROM track_metadata
                WHERE name = %s AND (%s::boolean IS NULL OR hidden = %s)""",
            (name, hidden, hidden),
        )

    def list(self, hidden: bool | None = False) -> list[Row]:
        """List visible, hidden, or all records newest first."""
        return self.fetch_all(
            f"""SELECT {self.COLUMNS} FROM track_metadata
                WHERE %s::boolean IS NULL OR hidden = %s
                ORDER BY updated_at DESC, name""",
            (hidden, hidden),
        )

    def list_favorites(self) -> list[Row]:
        """List visible favorite tracks newest first."""
        return self.fetch_all(
            f"""SELECT {self.COLUMNS} FROM track_metadata
                WHERE favorite = true AND hidden = false
                ORDER BY updated_at DESC, name"""
        )

    def is_hidden(self, name: str) -> bool:
        """Return whether the named track belongs to the Hidden Vault."""
        row = self.fetch_one("SELECT hidden FROM track_metadata WHERE name = %s", (name,))
        if row is None:
            raise FileNotFoundError(f"Track {name!r} was not found.")
        return bool(row["hidden"])

    def find_visible_by_content(self, content_sha256: str) -> Row | None:
        """Return the newest visible track with identical bytes, if any."""
        return self.fetch_one(
            f"""SELECT {self.COLUMNS} FROM track_metadata
                WHERE content_sha256 = %s AND hidden = false
                ORDER BY updated_at DESC, name LIMIT 1""",
            (content_sha256,),
        )

    def name_for_track_id(self, track_id: str) -> str | None:
        """Resolve an immutable public identifier to its current filename."""
        row = self.fetch_one(
            "SELECT name FROM track_metadata WHERE track_id::text = %s", (track_id,)
        )
        return row["name"] if row else None

    def delete(self, name: str) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM track_metadata WHERE name = %s", (name,))

    def beats(self, content_sha256: str) -> Row | None:
        """The stored beat map of a file, if it was worked out before."""
        return self.fetch_one(
            "SELECT tempo_bpm, beats, strengths FROM track_beats WHERE content_sha256 = %s",
            (content_sha256,),
        )

    def save_beats(self, content_sha256: str, beat_map: Row) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO track_beats (content_sha256, tempo_bpm, beats, strengths)
                VALUES (%s, %s, %s, %s) ON CONFLICT (content_sha256) DO NOTHING""",
                (content_sha256, beat_map["tempo_bpm"], beat_map["beats"], beat_map["strengths"]),
            )

    def rename(self, name: str, new_name: str) -> Row:
        """Rename one visible record while preserving all other fields."""
        vector = search_vector_sql("%s", "caption", "array_to_string(tags, ' ')")
        try:
            row = self.fetch_one(
                f"""UPDATE track_metadata
                    SET name = %s, search_vector = {vector}, updated_at = now()
                    WHERE name = %s AND hidden = false
                    RETURNING {self.COLUMNS}""",
                (new_name, new_name, name),
            )
        except psycopg.errors.UniqueViolation as error:
            raise FileExistsError(f"Track {new_name!r} already exists.") from error
        if row is None:
            raise FileNotFoundError(f"Visible track {name!r} was not found.")
        return row

    def update_metadata(
        self, name: str, caption: str, tags: list[str], hidden: bool = False
    ) -> Row:
        """Update editable metadata and rebuild its full-text search vector."""
        vector = search_vector_sql("name", "%s", "array_to_string(%s::text[], ' ')")
        row = self.fetch_one(
            f"""UPDATE track_metadata
                SET caption = %s, tags = %s, search_vector = {vector}, updated_at = now()
                WHERE name = %s AND hidden = %s
                RETURNING {self.COLUMNS}""",
            (caption, tags, caption, tags, name, hidden),
        )
        if row is None:
            raise FileNotFoundError(f"Track {name!r} was not found.")
        return row

    def embeddings(self, names: list[str]) -> dict[str, list[float]]:
        """The CLAP embeddings of visible tracks, by name (tracks without one are left out)."""
        rows = self.fetch_all(
            """SELECT name, embedding::text AS embedding FROM track_metadata
               WHERE name = ANY(%s) AND hidden = false AND embedding IS NOT NULL""",
            (names,),
        )
        return {row["name"]: [float(value) for value in row["embedding"].strip("[]").split(",")] for row in rows}

    def set_cover(self, name: str, cover_url: str | None) -> Row:
        """Set or clear a visible track's cover image (a Luna Visia public URL)."""
        row = self.fetch_one(
            f"""UPDATE track_metadata SET cover_url = %s, updated_at = now()
                WHERE name = %s AND hidden = false RETURNING {self.COLUMNS}""",
            (cover_url, name),
        )
        if row is None:
            raise FileNotFoundError(f"Visible track {name!r} was not found.")
        return row

    def set_hidden(self, names: list[str], hidden: bool) -> list[str]:
        """Persist hidden state and return the names that actually changed."""
        if not names:
            return []
        rows = self.fetch_all(
            """UPDATE track_metadata SET hidden = %s, updated_at = now()
               WHERE name = ANY(%s) AND hidden <> %s RETURNING name""",
            (hidden, names, hidden),
        )
        return [row["name"] for row in rows]

    def set_favorite(self, names: list[str], favorite: bool) -> list[str]:
        """Set favorite state for visible tracks and return the changed names."""
        if not names:
            return []
        rows = self.fetch_all(
            """UPDATE track_metadata SET favorite = %s, updated_at = now()
               WHERE name = ANY(%s) AND hidden = false AND favorite <> %s
               RETURNING name""",
            (favorite, names, favorite),
        )
        return [row["name"] for row in rows]

    RESULT_FIELDS = (
        "name", "caption", "tags", "favorite", "duration_seconds", "tempo_bpm", "musical_key",
        "energy", "cover_url", "updated_at", "public_url",
    )

    def search(
        self,
        normalized_query: str,
        tags: list[str],
        match_all_tags: bool,
        limit: int,
        offset: int,
        query_embedding: list[float] | None = None,
        semantic_weight: float = 0.75,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
    ) -> tuple[int, list[Row]]:
        """Rank visible tracks by meaning, words, or both, without opening any file.

        With a query embedding, every visible track is ranked by its CLAP similarity
        to the query blended with its full-text rank, so a description such as
        "evening coffee" finds tracks that sound right even when no stored word
        matches. Without one, only tracks whose words match are returned.
        """
        clauses = ["hidden = false"]
        filters: list[Any] = []
        if normalized_query and not query_embedding:
            clauses.append("search_vector @@ websearch_to_tsquery('english', %s)")
            filters.append(normalized_query)
        if tags:
            clauses.append(f"tags {'@>' if match_all_tags else '&&'} %s")
            filters.append(tags)
        if min_seconds is not None:
            clauses.append("duration_seconds >= %s")
            filters.append(min_seconds)
        if max_seconds is not None:
            clauses.append("duration_seconds <= %s")
            filters.append(max_seconds)
        rank_params: list[Any] = []
        text_rank = "0"
        if normalized_query:
            # ts_rank_cd is unbounded; x / (1 + x) maps it into 0-1 to blend with similarity.
            text_rank = "(ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) / " \
                        "(1 + ts_rank_cd(search_vector, websearch_to_tsquery('english', %s))))"
            rank_params += [normalized_query, normalized_query]
        if query_embedding:
            rank_sql = (
                f"(%s * coalesce(1 - (embedding <=> %s::vector), 0) + (1 - %s) * {text_rank})"
            )
            rank_params = [semantic_weight, vector_literal(query_embedding), semantic_weight] + rank_params
        else:
            rank_sql = text_rank
        rows = self.fetch_all(
            f"""SELECT {', '.join(self.RESULT_FIELDS)},
                       count(*) OVER() AS total_count, {rank_sql} AS rank
                FROM track_metadata WHERE {' AND '.join(clauses)}
                ORDER BY rank DESC, updated_at DESC, name LIMIT %s OFFSET %s""",
            rank_params + filters + [limit, offset],
        )
        count = rows[0]["total_count"] if rows else 0
        results = [
            {**{key: row[key] for key in self.RESULT_FIELDS}, "score": round(float(row["rank"]), 4)}
            for row in rows
        ]
        return count, results


class PublicURLRepository(Repository):
    """The mutable public origin and every track URL derived from it."""

    SELECT_BASE_URL = "SELECT public_base_url FROM vault_config WHERE singleton = true"

    def get(self) -> str:
        """Return the currently persisted public HTTPS origin."""
        row = self.fetch_one(self.SELECT_BASE_URL)
        return row["public_base_url"] if row else ""

    def seed(self, default_url: str) -> str:
        """Store ``default_url`` only when unset, then refresh stored track URLs."""
        with self.database.connect() as connection:
            if default_url:
                connection.execute(
                    """INSERT INTO vault_config (singleton, public_base_url)
                       VALUES (true, %s) ON CONFLICT (singleton) DO NOTHING""",
                    (default_url,),
                )
            row = connection.execute(self.SELECT_BASE_URL).fetchone()
            public_base_url = row["public_base_url"] if row else ""
            if public_base_url:
                self._regenerate(connection, public_base_url)
        return public_base_url

    def replace(self, public_base_url: str) -> int:
        """Atomically store the origin and regenerate every track URL."""
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO vault_config (singleton, public_base_url)
                   VALUES (true, %s)
                   ON CONFLICT (singleton) DO UPDATE SET
                       public_base_url = EXCLUDED.public_base_url,
                       updated_at = now()""",
                (public_base_url,),
            )
            return self._regenerate(connection, public_base_url)

    @staticmethod
    def _regenerate(connection: psycopg.Connection, public_base_url: str) -> int:
        cursor = connection.execute(
            f"UPDATE track_metadata SET public_url = {public_url_sql('%s')}",
            (public_base_url,),
        )
        return cursor.rowcount


@dataclass(frozen=True)
class StoredCredentials:
    """Salted Hidden Vault password and reset-PIN hashes."""

    password_salt: bytes
    password_hash: bytes
    pin_salt: bytes
    pin_hash: bytes
    iterations: int


class CredentialRepository(Repository):
    """The single Hidden Vault credential record."""

    def get(self) -> StoredCredentials | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT password_salt, password_hash, reset_pin_salt AS pin_salt,
                          reset_pin_hash AS pin_hash, iterations
                   FROM vault_security WHERE singleton = true"""
            ).fetchone()
        return StoredCredentials(**row) if row else None

    def create(self, credentials: StoredCredentials) -> bool:
        """Persist credentials only when none exist; report whether they were stored."""
        with self.database.connect() as connection:
            row = connection.execute(
                """INSERT INTO vault_security
                       (singleton, password_salt, password_hash, reset_pin_salt,
                        reset_pin_hash, iterations)
                   VALUES (true, %s, %s, %s, %s, %s)
                   ON CONFLICT (singleton) DO NOTHING RETURNING singleton""",
                (
                    credentials.password_salt,
                    credentials.password_hash,
                    credentials.pin_salt,
                    credentials.pin_hash,
                    credentials.iterations,
                ),
            ).fetchone()
        return row is not None

    def update_password(self, salt: bytes, password_hash: bytes, iterations: int) -> None:
        """Replace the stored password-derived credential material."""
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE vault_security SET password_salt = %s,
                       password_hash = %s, iterations = %s, updated_at = now()
                   WHERE singleton = true""",
                (salt, password_hash, iterations),
            )
