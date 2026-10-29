"""PostgreSQL connection handling and idempotent schema management."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

# CLAP's shared music-text space; every track and search query is embedded into it.
EMBEDDING_DIMENSIONS = 512

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS track_metadata (
    name text PRIMARY KEY,
    track_id uuid NOT NULL DEFAULT gen_random_uuid(),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    content_sha256 char(64) NOT NULL,
    caption text NOT NULL,
    tags text[] NOT NULL DEFAULT '{{}}',
    analysis_model text NOT NULL,
    audio_format text NOT NULL,
    duration_seconds real NOT NULL CHECK (duration_seconds >= 0),
    sample_rate integer,
    channels integer,
    bitrate integer,
    title text,
    artist text,
    notes text,
    tempo_bpm real,
    musical_key text,
    energy real,
    cover_url text,
    embedding vector({EMBEDDING_DIMENSIONS}),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    search_vector tsvector NOT NULL,
    hidden boolean NOT NULL DEFAULT false,
    favorite boolean NOT NULL DEFAULT false,
    public_url text
);
CREATE UNIQUE INDEX IF NOT EXISTS track_metadata_track_id_idx ON track_metadata (track_id);
CREATE INDEX IF NOT EXISTS track_metadata_search_idx ON track_metadata USING gin (search_vector);
CREATE INDEX IF NOT EXISTS track_metadata_tags_idx ON track_metadata USING gin (tags);
CREATE INDEX IF NOT EXISTS track_metadata_sha_idx ON track_metadata (content_sha256);
CREATE INDEX IF NOT EXISTS track_metadata_hidden_idx ON track_metadata (hidden, updated_at DESC);
CREATE INDEX IF NOT EXISTS track_metadata_favorite_idx
    ON track_metadata (favorite, hidden, updated_at DESC);
CREATE INDEX IF NOT EXISTS track_metadata_embedding_idx
    ON track_metadata USING hnsw (embedding vector_cosine_ops);
CREATE TABLE IF NOT EXISTS vault_security (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    password_salt bytea NOT NULL,
    password_hash bytea NOT NULL,
    reset_pin_salt bytea NOT NULL,
    reset_pin_hash bytea NOT NULL,
    iterations integer NOT NULL CHECK (iterations >= 100000),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vault_config (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    public_base_url text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


class Database:
    """Open short-lived transactional connections that return dict rows."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        """Yield one connection; its transaction commits when the block succeeds."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def initialize_schema(self) -> None:
        """Create or upgrade the idempotent Luna Vibia database schema."""
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            # pgvector is not a trusted extension: Luna Sentia's postgres-init installs it.
            if connection.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone() is None:
                raise RuntimeError(
                    "The pgvector extension is missing; run Luna Sentia's postgres-init to install it."
                )
            connection.execute(SCHEMA_SQL)
