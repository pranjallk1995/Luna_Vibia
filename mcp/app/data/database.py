"""PostgreSQL connection handling and idempotent schema management."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from app.core import tenancy
from app.data.tenants import TenantSchemas, use_space

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
-- An optional similarity order for the visible library (NULL = newest first).
ALTER TABLE track_metadata ADD COLUMN IF NOT EXISTS showcase_rank integer;
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
-- Beat maps for Luna Lumia's light pulses, worked out the first time a track is asked for.
CREATE TABLE IF NOT EXISTS track_beats (
    content_sha256 char(64) PRIMARY KEY,
    tempo_bpm real,
    beats real[] NOT NULL,
    strengths real[] NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
-- Saved playlists. Their tracks are kept by track_id, so renaming a track keeps it in
-- place, and deleting one removes it. Names are unique whatever their case.
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(trim(name)) > 0),
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS playlists_name_idx ON playlists (lower(name));
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id uuid NOT NULL REFERENCES playlists (playlist_id) ON DELETE CASCADE,
    track_id uuid NOT NULL REFERENCES track_metadata (track_id) ON DELETE CASCADE,
    position integer NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (playlist_id, track_id)
);
CREATE INDEX IF NOT EXISTS playlist_tracks_order_idx ON playlist_tracks (playlist_id, position);
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
        self.tenants = TenantSchemas(self.transaction, self.create_tables)

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection]:
        """Yield a connection to no one's data; its transaction commits when the block succeeds."""
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        """Yield one connection to the current person's schema, in one transaction."""
        user_id = tenancy.current()
        self.tenants.ensure(user_id)
        with self.transaction() as connection:
            use_space(connection, user_id)
            yield connection

    def initialize_schema(self) -> None:
        """Give the owner any data from before there were users; schemas come on first use."""
        with self.transaction() as connection:
            # pgvector is not a trusted extension: Luna Sentia's postgres-init installs it.
            if connection.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone() is None:
                raise RuntimeError(
                    "The pgvector extension is missing; run Luna Sentia's postgres-init to install it."
                )
        self.tenants.adopt_public_tables()

    def create_tables(self, connection: psycopg.Connection) -> None:
        """Create or upgrade one person's idempotent Luna Vibia schema."""
        connection.execute(SCHEMA_SQL)
