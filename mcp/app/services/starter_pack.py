"""The starter pack: the starter library as one file, for a fresh install to begin with.

Exporting writes the owner's starter tracks to a ZIP: a manifest with each track's
caption, tags, credits, musical facts and CLAP embedding, the audio files, and each
track's cover art from Luna Visia. Hidden tracks and favorites are never included, as in
the starter library, and the pack is published for anyone, so only tracks the owner is
happy to give everyone belong in it.

A fresh install downloads the pack on its first start and adds the tracks to the owner's
library as their starter tracks, already described and searchable. Each cover is stored
in that install's Luna Visia; Visia answers a cover its own starter pack already added
with that image, so none is stored twice. Without LUNAVISIA_COMPANION_TOKEN the tracks
load without covers. Whether an install is fresh is decided before the server answers
anything; an install that had tracks, or has loaded the pack, never loads it again, and
one that has not finished tries again on its next start. The same as Luna Visia's.

    python -m app.services.starter_pack export /data/downloads/luna-vibia-starter-pack.zip
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.core import tenancy
from app.core.config import AppConfig
from app.data.database import Database
from app.data.repositories import PUBLIC_TRACK_PATH, search_vector_sql
from app.integrations.visia import VisiaImageCatalog

logger = logging.getLogger(__name__)

APP = "vibia"
PACK_FORMAT = 1
MANIFEST = "manifest.json"
FILES = "tracks/"
COVERS = "covers/"
PACKED_COLUMNS = (
    "name", "size_bytes", "content_sha256", "caption", "tags", "analysis_model", "audio_format",
    "duration_seconds", "sample_rate", "channels", "bitrate", "title", "artist", "notes", "tempo_bpm",
    "musical_key", "energy", "embedding", "showcase_rank",
)
# The states of an install's pack: still to load, loaded, or never needed.
PENDING, LOADED, SKIPPED = "pending", "loaded", "skipped"
DOWNLOAD_TIMEOUT = httpx.Timeout(60.0)
ATTEMPTS = 10
RETRY_SECONDS = 60.0


class StarterPack:
    def __init__(
        self, database: Database, track_dir: Path, allowed_suffixes: set[str], covers: VisiaImageCatalog
    ) -> None:
        self.database = database
        self.track_dir = track_dir
        self.allowed_suffixes = allowed_suffixes
        self.covers = covers

    @property
    def folder(self) -> Path:
        return self.track_dir / tenancy.space_name(tenancy.OWNER)

    def export(self, path: Path) -> int:
        """Write the owner's starter tracks and their covers to a pack at ``path``; returns how many."""
        columns = ", ".join(column for column in PACKED_COLUMNS if column != "embedding")
        with tenancy.acting_as(tenancy.OWNER):
            with self.database.connect() as connection:
                rows = connection.execute(
                    f"""SELECT {columns}, embedding::text AS embedding, cover_url FROM track_metadata
                        WHERE starter AND NOT hidden AND NOT favorite ORDER BY name"""
                ).fetchall()
            images = {str(image["image_id"]).lower(): image for image in self.covers.images()}
        tracks = []
        partial = path.with_name(path.name + ".part")
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as pack:
            for row in rows:
                file = self.folder / row["name"]
                data = file.read_bytes() if file.is_file() else None
                if data is None or hashlib.sha256(data).hexdigest() != row["content_sha256"].strip():
                    logger.warning("Leaving %s out: its file is missing or does not match.", row["name"])
                    continue
                track = {column: row[column] for column in PACKED_COLUMNS}
                track["cover"] = self.pack_cover(pack, row["cover_url"], images)
                pack.writestr(FILES + row["name"], data)
                tracks.append(track)
            pack.writestr(MANIFEST, json.dumps({"app": APP, "format": PACK_FORMAT, "tracks": tracks}, indent=1))
        partial.replace(path)
        return len(tracks)

    def pack_cover(self, pack: zipfile.ZipFile, cover_url: str | None, images: dict[str, dict]) -> str | None:
        """Add a track's cover to the pack and return its name; None for no cover or the placeholder."""
        if not cover_url or self.covers.is_placeholder(cover_url) or not self.covers.is_visia_url(cover_url):
            return None
        image_id = self.covers.image_id(cover_url)
        image = images.get(image_id)
        if image is None:
            logger.warning("Leaving out a cover Luna Visia no longer shows: %s", image_id)
            return None
        name = str(image["name"])
        if FILES + name not in pack.namelist() and COVERS + name not in pack.namelist():
            response = httpx.get(f"{self.covers.api_url}/api/public/images/{image_id}", timeout=60.0)
            response.raise_for_status()
            pack.writestr(COVERS + name, response.content)
        return name

    def decide(self, url: str) -> bool:
        """Note whether this install still has the pack to load; call before serving anything."""
        if not url:
            return False
        with tenancy.acting_as(tenancy.OWNER), self.database.connect() as connection:
            state = connection.execute("SELECT state FROM starter_pack").fetchone()
            if state is None:
                used = connection.execute("SELECT EXISTS (SELECT 1 FROM track_metadata) AS used").fetchone()
                state = {"state": SKIPPED if used["used"] else PENDING}
                connection.execute(
                    "INSERT INTO starter_pack (state, source) VALUES (%s, %s)", (state["state"], url)
                )
        return state["state"] == PENDING

    def load_in_background(self, url: str, after: Any = None) -> None:
        """Load the pack, retrying a failed download or an unreachable Visia; then call ``after``."""
        for attempt in range(ATTEMPTS):
            try:
                count = self.load_from(url)
            except Exception:  # noqa: BLE001 - logged, and the next start tries again.
                logger.exception("Could not load the starter pack (attempt %d of %d).", attempt + 1, ATTEMPTS)
                time.sleep(RETRY_SECONDS)
                continue
            logger.info("Loaded %d starter tracks from the starter pack.", count)
            if after is not None:
                after()
            return
        logger.warning("Gave up on the starter pack for now; the next start tries again.")

    def load_from(self, url: str) -> int:
        with tempfile.TemporaryDirectory() as scratch:
            pack = Path(scratch) / "pack.zip"
            with httpx.stream("GET", url, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT) as response:
                response.raise_for_status()
                with pack.open("wb") as out:
                    for chunk in response.iter_bytes(1 << 20):
                        out.write(chunk)
            return self.load(pack)

    def load(self, path: Path) -> int:
        """Add a pack's tracks to the owner's library as starter tracks; returns how many.

        A name already in use keeps its track. Tracks whose bytes do not match the
        manifest are left out.
        """
        given = 0
        vector = search_vector_sql(
            "%(name)s", "%(caption)s", "array_to_string(%(tags)s::text[], ' ')",
            "concat_ws(' ', %(title)s::text, %(artist)s::text)",
        )
        with zipfile.ZipFile(path) as pack, tenancy.acting_as(tenancy.OWNER):
            manifest = json.loads(pack.read(MANIFEST))
            if manifest.get("app") != APP or manifest.get("format") != PACK_FORMAT:
                raise ValueError("This is not a Luna Vibia starter pack this version can read.")
            self.folder.mkdir(parents=True, exist_ok=True)
            if not self.covers.companion_token:
                logger.warning("Loading the starter tracks without covers: LUNAVISIA_COMPANION_TOKEN is not set.")
            with self.database.connect() as connection:
                base = connection.execute("SELECT public_base_url FROM vault_config").fetchone()
                have = {row["name"] for row in connection.execute("SELECT name FROM track_metadata")}
                for track in manifest["tracks"]:
                    name = str(track["name"])
                    if name in have:
                        continue
                    if Path(name).name != name or name.startswith(".") or Path(name).suffix.lower() not in self.allowed_suffixes:
                        logger.warning("Leaving out a starter track with an unusable name: %r", name)
                        continue
                    data = pack.read(FILES + name)
                    if hashlib.sha256(data).hexdigest() != track["content_sha256"].strip():
                        logger.warning("Leaving out starter track %s: it does not match the manifest.", name)
                        continue
                    track_id = uuid4()
                    values = {
                        **{column: track.get(column) for column in PACKED_COLUMNS},
                        "name": name,
                        "size_bytes": len(data),
                        "track_id": track_id,
                        "public_url": f"{base['public_base_url']}{PUBLIC_TRACK_PATH}{track_id}" if base else None,
                        "cover_url": self.store_cover(pack, name, track.get("cover")),
                    }
                    columns = ", ".join(column for column in PACKED_COLUMNS if column != "embedding")
                    placeholders = ", ".join(f"%({column})s" for column in PACKED_COLUMNS if column != "embedding")
                    added = connection.execute(
                        f"""INSERT INTO track_metadata
                               ({columns}, embedding, track_id, public_url, cover_url, starter, search_vector)
                            VALUES ({placeholders}, %(embedding)s::vector, %(track_id)s, %(public_url)s,
                                    %(cover_url)s, true, {vector})
                            ON CONFLICT (name) DO NOTHING RETURNING name""",
                        values,
                    ).fetchone()
                    if added:
                        write_file(self.folder / name, data)
                        given += 1
                connection.execute("UPDATE starter_pack SET state = %s, loaded_at = now()", (LOADED,))
        return given

    def store_cover(self, pack: zipfile.ZipFile, track: str, cover: str | None) -> str | None:
        """Store a track's cover in Luna Visia and return its public URL; None without one."""
        if not cover or not self.covers.companion_token:
            return None
        stem = Path(track).stem
        tags = [*VisiaImageCatalog.APP_TAGS, stem.replace("_", " ").casefold()]
        content = base64.b64encode(pack.read(COVERS + cover)).decode("ascii")
        stored = self.covers.store(Path(cover).stem, tags, {"content_base64": content})
        return stored.get("public_url")


def write_file(target: Path, data: bytes) -> None:
    """Write a whole file, so a reader never sees half of one."""
    partial = target.with_name(f".{target.name}.{uuid4().hex}.part")
    partial.write_bytes(data)
    os.replace(partial, target)


def main(arguments: list[str]) -> None:
    if len(arguments) != 2 or arguments[0] != "export":
        raise SystemExit("Usage: python -m app.services.starter_pack export <pack.zip>")
    logging.basicConfig(level=logging.INFO)
    config = AppConfig.from_env()
    covers = VisiaImageCatalog(
        config.visia_api_url, config.placeholder_cover_id, companion_token=config.visia_companion_token
    )
    pack = StarterPack(Database(config.database_url), config.track_dir, set(config.allowed_formats), covers)
    count = pack.export(Path(arguments[1]))
    print(f"Wrote {count} starter tracks to {arguments[1]}.")


if __name__ == "__main__":
    main(sys.argv[1:])
