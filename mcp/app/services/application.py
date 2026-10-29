"""Luna Vibia use cases, independent of the HTTP and MCP transports."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np

from app.core.config import AppConfig
from app.services.analysis_graph import TrackAnalysisGraph
from app.services.downloads import DownloadStore, DownloadTicket
from app.services.inspection import TrackInspector
from app.services.media import TrackPayloadDecoder
from app.core.models import TrackAnalysis, TrackRecord, MetadataChange, MetadataRules
from app.data.repositories import TrackRepository, PublicURLRepository, Row
from app.data.storage import TrackStorage
from app.services.uploads import UploadLinkStore
from app.integrations.captioning import OllamaCaptioner
from app.integrations.clap import ClapEncoder
from app.integrations.speakers import Speaker, SpeakerPlayer
from app.integrations.visia import VisiaImageCatalog


# The compact view of a track returned to LLM clients when listing or searching.
SUMMARY_FIELDS = (
    "name", "caption", "tags", "favorite", "title", "artist", "duration_seconds", "tempo_bpm",
    "musical_key", "energy", "cover_url", "updated_at", "public_url",
)


def summarize(row: Row, fields: tuple[str, ...] = SUMMARY_FIELDS) -> Row:
    return {key: row[key] for key in fields if key in row}


def page(items: list[Row], total: int, limit: int, offset: int) -> dict[str, Any]:
    """Wrap one page of results with the offset of the next page, if any."""
    next_offset = offset + len(items)
    return {
        "count": total,
        "offset": offset,
        "next_offset": next_offset if next_offset < total else None,
        "tracks": items,
    }


def unique_names(names: list[str], empty_message: str) -> list[str]:
    """Return ``names`` deduplicated in order, rejecting an empty selection."""
    if not isinstance(names, list) or not names:
        raise ValueError(empty_message)
    return list(dict.fromkeys(names))


class PublicURLService:
    """Validate and persist the HTTPS origin that every track URL derives from."""

    def __init__(self, repository: PublicURLRepository) -> None:
        self.repository = repository

    @staticmethod
    def validate(public_base_url: str) -> str:
        """Normalize and validate a public HTTPS origin and optional path prefix."""
        normalized = public_base_url.strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "public_base_url must be an HTTPS URL without credentials, "
                "a query, or a fragment."
            )
        return normalized

    def seed(self, default_url: str) -> str:
        return self.repository.seed(default_url)

    def base_url(self) -> str:
        public_base_url = self.repository.get()
        if not public_base_url:
            raise RuntimeError("The Luna Vibia public base URL is not configured.")
        return public_base_url

    def update(self, public_base_url: str) -> dict[str, Any]:
        """Persist a new HTTPS origin and regenerate all stored track URLs."""
        normalized = self.validate(public_base_url)
        return {
            "status": "public_base_url_updated",
            "public_base_url": normalized,
            "updated_track_count": self.repository.replace(normalized),
        }


class TrackIndexer:
    """Analyze track bytes and persist the result with content identity.

    Analysis runs as the ``TrackAnalysisGraph``: measure the file, listen with
    CLAP and check provenance in parallel, then caption and tag.
    """

    AI_MODIFIED_TAG = TrackAnalysisGraph.AI_MODIFIED_TAG
    AI_INFO_TAG = TrackAnalysisGraph.AI_INFO_TAG

    def __init__(
        self,
        storage: TrackStorage,
        tracks: TrackRepository,
        captioner: OllamaCaptioner,
        encoder: ClapEncoder,
        urls: PublicURLService,
        inspector: TrackInspector,
        rules: MetadataRules,
    ) -> None:
        self.storage = storage
        self.tracks = tracks
        self.captioner = captioner
        self.encoder = encoder
        self.urls = urls
        self.inspector = inspector
        self.rules = rules
        self.graph = TrackAnalysisGraph(captioner, encoder, inspector, rules)

    @property
    def model(self) -> str:
        """Both models that shape a record; a change in either re-analyzes on backfill."""
        return f"{self.captioner.model} + {self.encoder.model_name.rsplit('/', 1)[-1]}"

    def analyze(self, data: bytes, modified: bool = False, given: dict[str, str] | None = None) -> TrackAnalysis:
        """Analyze bytes, tagging replacements and AI-generated tracks.

        ``given`` holds a title, artist, or generator notes supplied with the
        upload; they are stored and help the caption.
        """
        return self.graph.run(data, modified, given)

    def store(self, name: str, data: bytes, analysis: TrackAnalysis) -> Row:
        record = TrackRecord(
            name=name,
            size_bytes=len(data),
            content_sha256=hashlib.sha256(data).hexdigest(),
            caption=analysis.caption,
            tags=list(analysis.tags),
            analysis_model=self.model,
            facts=analysis.facts,
            embedding=analysis.embedding,
        )
        return self.tracks.upsert(record, self.urls.base_url())

    def backfill(self) -> dict[str, Any]:
        """Analyze unindexed, changed, or other-model files while skipping current records.

        A re-analyzed track keeps its ``ai modified`` tag and its title, artist,
        and generator notes. Current records are not re-analyzed, but
        AI-generated ones missing the ``ai info`` tag get it added.
        """
        indexed = {item["name"]: item for item in self.tracks.list(hidden=None)}
        analyzed, ai_tagged = [], []
        skipped = 0
        for path in self.storage.track_files():
            data = path.read_bytes()
            existing = indexed.get(path.name)
            if (
                existing
                and existing["content_sha256"] == hashlib.sha256(data).hexdigest()
                and existing["analysis_model"] == self.model
            ):
                skipped += 1
                if self.AI_INFO_TAG not in existing["tags"] and self.inspector.is_ai_generated(data):
                    self.tracks.update_metadata(
                        path.name,
                        existing["caption"],
                        self.rules.with_tags(existing["tags"], [self.AI_INFO_TAG]),
                        hidden=existing["hidden"],
                    )
                    ai_tagged.append(path.name)
                continue
            modified = bool(existing) and self.AI_MODIFIED_TAG in existing["tags"]
            given = {key: existing[key] for key in ("title", "artist", "notes")} if existing else None
            self.store(path.name, data, self.analyze(data, modified, given))
            analyzed.append(path.name)
        return {
            "analyzed_count": len(analyzed),
            "skipped_count": skipped,
            "analyzed": analyzed,
            "ai_tagged_count": len(ai_tagged),
            "ai_tagged": ai_tagged,
        }


class TrackCollectionService:
    """Operations shared by the visible library and the Hidden Vault.

    Each subclass is bound to one side of the ``hidden`` flag and refuses to
    touch tracks that belong to the other side.
    """

    HIDDEN: bool
    WRONG_COLLECTION_MESSAGE: str
    AI_INFO_REQUIRED_MESSAGE = (
        f"The {TrackIndexer.AI_INFO_TAG!r} tag cannot be removed: this track's embedded "
        "metadata marks it as AI-generated."
    )

    def __init__(
        self,
        storage: TrackStorage,
        tracks: TrackRepository,
        rules: MetadataRules,
        inspector: TrackInspector,
    ) -> None:
        self.storage = storage
        self.tracks = tracks
        self.rules = rules
        self.inspector = inspector

    def path(self, name: str) -> Path:
        """Return the file for a track in this collection or reject access."""
        path = self.storage.existing_path(name)
        if self.tracks.is_hidden(name) != self.HIDDEN:
            raise PermissionError(self.WRONG_COLLECTION_MESSAGE)
        return path

    def get(self, name: str) -> Row:
        row = self.tracks.get(name, hidden=self.HIDDEN)
        if row is None:
            raise FileNotFoundError(f"Track {name!r} was not found.")
        return row

    def list(self) -> list[Row]:
        return self.tracks.list(hidden=self.HIDDEN)

    def update_metadata(self, name: str, change: MetadataChange) -> Row:
        """Explicitly edit a caption and/or searchable tags.

        AI-generated tracks always keep the ``ai info`` tag: removing it is
        rejected, and a track that lacks it gets it back on any edit.
        """
        path = self.path(name)
        if change.is_empty:
            raise ValueError("Provide a caption, add_tags, or remove_tags change.")
        current = self.get(name)
        caption = (
            current["caption"] if change.caption is None else self.rules.caption(change.caption)
        )
        tags = self.rules.edited_tags(current["tags"], change.add_tags, change.remove_tags)
        ai_tag = TrackIndexer.AI_INFO_TAG
        if ai_tag not in tags and self.inspector.is_ai_generated(path.read_bytes()):
            if ai_tag in current["tags"]:
                raise ValueError(self.AI_INFO_REQUIRED_MESSAGE)
            tags = self.rules.with_tags(tags, [ai_tag])
        return self.tracks.update_metadata(name, caption, tags, hidden=self.HIDDEN)

    def remove(self, name: str) -> dict[str, str]:
        """Delete a track and its metadata, restoring the file on failure."""
        with self.storage.removing(self.path(name)):
            self.tracks.delete(name)
        return {"status": "deleted", "removed_name": name}


class VisibleTrackService(TrackCollectionService):
    """The public library: ingest, rename, favorites, and public delivery."""

    HIDDEN = False
    WRONG_COLLECTION_MESSAGE = "Hidden tracks require authentication."
    RENAME_STEM_PATTERN = re.compile(r"[A-Za-z0-9_]+")

    def __init__(
        self,
        storage: TrackStorage,
        tracks: TrackRepository,
        rules: MetadataRules,
        decoder: TrackPayloadDecoder,
        indexer: TrackIndexer,
        inspector: TrackInspector,
        covers: VisiaImageCatalog,
        max_fetch_tracks: int,
        max_fetch_bytes: int,
    ) -> None:
        super().__init__(storage, tracks, rules, inspector)
        self.decoder = decoder
        self.indexer = indexer
        self.covers = covers
        self.max_fetch_tracks = max_fetch_tracks
        self.max_fetch_bytes = max_fetch_bytes

    def ingest(
        self, name: str, content_base64: str, replace: bool = False, given: dict[str, str] | None = None
    ) -> Row:
        """Create or replace a track from Base64 under exactly ``name``."""
        return self.ingest_bytes(name, self.decoder.decode_base64(content_base64), replace, given)

    def ingest_bytes(
        self, name: str, data: bytes, replace: bool = False, given: dict[str, str] | None = None
    ) -> Row:
        """Create or replace a track and persist matching AI metadata."""
        path = self.storage.path(name)
        self.decoder.validate(name, data)
        exists = path.is_file()
        if replace and not exists:
            raise FileNotFoundError(f"Track {name!r} was not found.")
        if replace and self.tracks.is_hidden(name):
            raise PermissionError(self.WRONG_COLLECTION_MESSAGE)
        if not replace and exists:
            raise FileExistsError(f"Track {name!r} already exists; use modify_track.")
        if replace and not given:
            current = self.get(name)
            given = {key: current[key] for key in ("title", "artist", "notes")}
        analysis = self.indexer.analyze(data, modified=replace, given=given)
        with self.storage.writing(path, data):
            return self.indexer.store(name, data, analysis)

    def upload(
        self, requested_name: str | None, data: bytes, given: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Add chat-supplied bytes, adapting the name instead of rejecting it.

        The extension follows the detected format, a taken name gets a numeric
        suffix, and bytes identical to a visible track are reported as a
        duplicate rather than stored twice (LLM clients often retry uploads).
        """
        detected = self.decoder.detect_format(data)
        duplicate = self.tracks.find_visible_by_content(hashlib.sha256(data).hexdigest())
        if duplicate is not None:
            return {
                "status": "duplicate",
                "message": f"This track is already stored as {duplicate['name']!r}.",
                **duplicate,
            }
        name = self.storage.available_name(self.decoder.name_for(requested_name, detected))
        result = {"status": "created", **self.ingest_bytes(name, data, given=given)}
        if requested_name and name != requested_name:
            result["requested_name"] = requested_name
        return result

    def upload_with_cover(
        self,
        requested_name: str | None,
        data: bytes,
        given: dict[str, str] | None,
        cover_url: str | None,
    ) -> dict[str, Any]:
        """Upload from an LLM client: a new track always gets a Visia cover or the placeholder.

        The cover is checked before the slow analysis, so a bad URL fails fast.
        A duplicate keeps the cover it already has.
        """
        cover = self.cover_or_placeholder(cover_url)
        result = self.upload(requested_name, data, given)
        if result["status"] == "created" and cover:
            result["cover_url"] = self.tracks.set_cover(result["name"], cover)["cover_url"]
        return result

    def cover_or_placeholder(self, cover_url: str | None) -> str | None:
        """Visia's canonical URL for ``cover_url``, or the audio placeholder when none was given."""
        if cover_url and cover_url.strip():
            return self.covers.resolve(cover_url)
        return self.covers.placeholder_url()

    def rename(self, name: str, new_name: str) -> dict[str, Any]:
        """Rename a track, keeping its extension, immutable ID, and public URL."""
        source = self.path(name)
        destination = self.storage.path(new_name)
        if not self.RENAME_STEM_PATTERN.fullmatch(destination.stem):
            raise ValueError(
                "The new filename may contain only letters, numbers, and "
                "underscores before the track extension."
            )
        if source == destination:
            raise ValueError("The new track name must be different from the current name.")
        if source.suffix.lower() != destination.suffix.lower():
            raise ValueError("Renaming cannot change the track file extension.")
        if destination.exists():
            raise FileExistsError(f"Track {new_name!r} already exists.")
        with self.storage.renaming(source, destination):
            metadata = self.tracks.rename(name, new_name)
        return {"status": "renamed", "old_name": name, **metadata}

    def metadata(self, name: str) -> dict[str, Any]:
        """Return the stored record plus everything embedded in the track file."""
        path = self.path(name)
        return {**self.get(name), **self.inspector.inspect(path.read_bytes())}

    def _describe(self, row: Row, detail: str) -> Row:
        """Combine one record with its embedded metadata at the requested detail."""
        try:
            inspected = self.inspector.inspect(self.storage.existing_path(row["name"]).read_bytes())
        except (OSError, ValueError, SyntaxError):
            return {**summarize(row), "embedded": {"error": "The track file could not be read."}}
        if detail == "full":
            return {**row, **inspected}
        return {**summarize(row), "embedded": self.inspector.summarize(inspected)}

    def metadata_page(
        self,
        limit: int,
        offset: int,
        max_limit: int,
        names: list[str] | None = None,
        detail: str = "summary",
    ) -> dict[str, Any]:
        """Return stored and embedded metadata for a page or an explicit batch.

        Full detail is capped at ``AppConfig.FULL_DETAIL_MAX_TRACKS`` because complete
        file-tag output is large; summaries allow up to ``max_limit``.
        """
        if detail not in ("summary", "full"):
            raise ValueError('detail must be "summary" or "full".')
        max_limit = min(max_limit, AppConfig.FULL_DETAIL_MAX_TRACKS) if detail == "full" else max_limit
        if names is None:
            rows = self.list()
            limit, offset = min(max(limit, 1), max_limit), max(offset, 0)
            selected = rows[offset : offset + limit]
            return page([self._describe(row, detail) for row in selected], len(rows), limit, offset)
        if any(not isinstance(name, str) for name in names):
            raise ValueError("Every track name must be a string.")
        clean_names = unique_names(names, "Provide at least one track name.")
        if len(clean_names) > max_limit:
            raise ValueError(f"Request metadata for at most {max_limit} tracks at a time.")
        rows = [self.tracks.get(name, hidden=False) for name in clean_names]
        result = page(
            [self._describe(row, detail) for row in rows if row is not None],
            len(clean_names),
            len(clean_names),
            0,
        )
        unavailable = [name for name, row in zip(clean_names, rows) if row is None]
        if unavailable:
            result["unavailable"] = unavailable
        return result

    def _apply_batch(
        self, items: list[tuple[str, Callable[[], Row]]], result_key: str
    ) -> dict[str, Any]:
        """Apply each change on its own, reporting failures instead of stopping."""
        if not items:
            raise ValueError("Provide at least one track change.")
        if len(items) > AppConfig.BATCH_MAX_TRACKS:
            raise ValueError(f"Change at most {AppConfig.BATCH_MAX_TRACKS} tracks at a time.")
        succeeded, failed = [], []
        for name, apply in items:
            try:
                succeeded.append(apply())
            except (FileNotFoundError, FileExistsError, PermissionError, ValueError) as error:
                failed.append({"name": name, "error": str(error)})
        return {
            f"{result_key}_count": len(succeeded),
            "failed_count": len(failed),
            result_key: succeeded,
            "failed": failed,
        }

    def update_metadata_many(self, changes: list[tuple[str, MetadataChange]]) -> dict[str, Any]:
        """Edit captions and tags of many visible tracks in one call."""
        return self._apply_batch(
            [
                (name, lambda name=name, change=change: summarize(self.update_metadata(name, change)))
                for name, change in changes
            ],
            "updated",
        )

    def rename_many(self, renames: list[tuple[str, str]]) -> dict[str, Any]:
        """Rename many visible tracks in order, so chained renames work."""

        def rename(name: str, new_name: str) -> Row:
            renamed = self.rename(name, new_name)
            return {"old_name": name, "name": renamed["name"], "public_url": renamed["public_url"]}

        return self._apply_batch(
            [
                (name, lambda name=name, new_name=new_name: rename(name, new_name))
                for name, new_name in renames
            ],
            "renamed",
        )

    def favorites(self) -> list[Row]:
        return self.tracks.list_favorites()

    def set_cover(self, name: str, cover_url: str | None, placeholder: bool = False) -> Row:
        """Set a track's cover to a Luna Visia image (verified there).

        Without a cover_url the cover is cleared, or with ``placeholder`` set to
        the audio placeholder in Visia (still cleared while none is configured).
        """
        self.path(name)
        if placeholder:
            resolved = self.cover_or_placeholder(cover_url)
        else:
            resolved = self.covers.resolve(cover_url) if cover_url and cover_url.strip() else None
        return summarize(self.tracks.set_cover(name, resolved))

    def stats(self, top_tags: int = 10) -> dict[str, Any]:
        """Summarize the visible library from stored metadata, without opening files.

        AI counts follow the system tags: ``ai info`` marks tracks whose embedded
        provenance says AI made them, ``ai modified`` marks replaced tracks.
        """
        rows = self.list()
        total_bytes = sum(row["size_bytes"] for row in rows)
        total_seconds = sum(row["duration_seconds"] or 0 for row in rows)
        formats = Counter(row["audio_format"] for row in rows)
        tags = Counter(tag for row in rows for tag in row["tags"])
        largest = max(rows, key=lambda row: row["size_bytes"], default=None)
        updated = sorted(str(row["updated_at"]) for row in rows)
        return {
            "total_tracks": len(rows),
            "favorite_count": sum(1 for row in rows if row["favorite"]),
            "ai_generated_count": sum(1 for row in rows if TrackIndexer.AI_INFO_TAG in row["tags"]),
            "ai_modified_count": sum(
                1 for row in rows if TrackIndexer.AI_MODIFIED_TAG in row["tags"]
            ),
            "with_cover_count": sum(1 for row in rows if row["cover_url"]),
            "total_duration_seconds": round(total_seconds, 1),
            "total_duration": self.human_duration(total_seconds),
            "total_size_bytes": total_bytes,
            "total_size": self.human_bytes(total_bytes),
            "average_size_bytes": total_bytes // len(rows) if rows else 0,
            "largest_track": (
                {
                    "name": largest["name"],
                    "size_bytes": largest["size_bytes"],
                    "size": self.human_bytes(largest["size_bytes"]),
                }
                if largest
                else None
            ),
            "formats": dict(formats.most_common()),
            "unique_tag_count": len(tags),
            "top_tags": [
                {"tag": tag, "count": count}
                for tag, count in tags.most_common(max(top_tags, 0))
            ],
            "oldest_updated_at": updated[0] if updated else None,
            "newest_updated_at": updated[-1] if updated else None,
        }

    @staticmethod
    def human_duration(seconds: float) -> str:
        minutes, second = divmod(int(round(seconds)), 60)
        hours, minute = divmod(minutes, 60)
        return f"{hours}h {minute:02d}m" if hours else f"{minute}m {second:02d}s"

    @staticmethod
    def human_bytes(size: int) -> str:
        """Format a byte count with the largest binary unit that keeps it >= 1."""
        value = float(size)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024:
                return f"{size} B" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} TiB"

    def list_page(self, limit: int, offset: int, max_limit: int) -> dict[str, Any]:
        """Return one page of compact track summaries, newest first."""
        rows = self.list()
        limit, offset = min(max(limit, 1), max_limit), max(offset, 0)
        return page([summarize(row) for row in rows[offset : offset + limit]], len(rows), limit, offset)

    def set_favorite(self, names: list[str], favorite: bool) -> dict[str, Any]:
        """Add visible tracks to Favorites or remove them."""
        clean_names = unique_names(names, "Select at least one track.")
        for name in clean_names:
            self.path(name)
        changed = self.tracks.set_favorite(clean_names, favorite)
        return {
            "status": "favorited" if favorite else "unfavorited",
            "names": changed,
            "count": len(changed),
        }

    def public_url(self, name: str) -> str:
        self.path(name)
        return self.get(name)["public_url"]

    def public_path(self, identifier: str) -> Path:
        """Resolve a stable track ID, with legacy filename compatibility."""
        return self.path(self.tracks.name_for_track_id(identifier) or identifier)

    def select_paths(
        self,
        names: list[str],
        max_tracks: int | None = None,
        max_bytes: int | None = None,
    ) -> list[Path]:
        """Resolve a bounded, deduplicated batch of visible track paths.

        Limits default to the chat-display bounds; callers that do not embed
        track bytes in a tool result (such as ZIP downloads) pass larger ones.
        """
        max_tracks = max_tracks or self.max_fetch_tracks
        max_bytes = max_bytes or self.max_fetch_bytes
        if isinstance(names, list) and any(not isinstance(name, str) for name in names):
            raise ValueError("Every track name must be a string.")
        clean_names = unique_names(names, "Provide at least one track name.")
        if len(clean_names) > max_tracks:
            raise ValueError(f"Fetch at most {max_tracks} tracks at a time.")
        paths = [self.path(name) for name in clean_names]
        if sum(path.stat().st_size for path in paths) > max_bytes:
            raise ValueError(
                f"Selected tracks exceed the {self.format_bytes(max_bytes)} limit; "
                "request fewer tracks."
            )
        return paths

    @staticmethod
    def format_bytes(size: int) -> str:
        if size >= 1024**3 and size % 1024**3 == 0:
            return f"{size // 1024**3} GiB"
        return f"{size / 1024**2:.0f} MiB"


class TrackDownloadService:
    """Package visible tracks as a ZIP behind a short-lived public download link.

    Archives are never embedded in tool results: MCP clients reject large
    messages, and chat apps cannot hand an embedded blob to the user as a file.
    """

    DOWNLOAD_PATH = "/api/downloads/"

    def __init__(
        self,
        visible: VisibleTrackService,
        store: DownloadStore,
        urls: PublicURLService,
        max_tracks: int,
        max_bytes: int,
    ) -> None:
        self.visible = visible
        self.store = store
        self.urls = urls
        self.max_tracks = max_tracks
        self.max_bytes = max_bytes

    def create_zip(self, names: list[str]) -> dict[str, Any]:
        """Archive the named visible tracks and return their download link."""
        base_url = self.urls.base_url()
        paths = self.visible.select_paths(names, self.max_tracks, self.max_bytes)
        ticket = self.store.create(paths)
        return {
            "status": "zip_ready",
            "download_url": f"{base_url}{self.DOWNLOAD_PATH}{ticket.token}",
            "file_name": ticket.file_name,
            "track_count": ticket.track_count,
            "size_bytes": ticket.size_bytes,
            "expires_at": ticket.expires_at_iso,
            "names": [path.name for path in paths],
        }

    def archive(self, token: str) -> tuple[DownloadTicket, Path]:
        """Return the live ticket and archive file for a download token."""
        return self.store.resolve(token), self.store.archive_path(token)


class UploadLinkService:
    """Let HTTP-capable clients upload file bytes instead of Base64 tool arguments.

    LLMs cannot emit megabytes of Base64, but agents with a shell or code
    sandbox can POST a local file to a single-use link.
    """

    UPLOAD_PATH = "/api/uploads/"

    def __init__(
        self,
        visible: VisibleTrackService,
        store: UploadLinkStore,
        urls: PublicURLService,
        max_bytes: int,
    ) -> None:
        self.visible = visible
        self.store = store
        self.urls = urls
        self.max_bytes = max_bytes

    def create_link(self, name: str, replace: bool = False) -> dict[str, Any]:
        if replace:
            self.visible.path(name)
        ticket = self.store.create(name, replace)
        url = f"{self.urls.base_url()}{self.UPLOAD_PATH}{ticket.token}"
        return {
            "status": "upload_link_ready",
            "upload_url": url,
            "method": "POST",
            "name": name,
            "replace": replace,
            "max_bytes": self.max_bytes,
            "expires_at": ticket.expires_at_iso,
            "usage": (
                "POST the raw file bytes or a multipart form field named 'file'. "
                "The link works once."
            ),
            "curl_example": f"curl -fsS -F 'file=@/path/to/track' '{url}'",
        }

    def receive(self, token: str, data: bytes, file_name: str | None = None) -> dict[str, Any]:
        """Store the uploaded bytes for a claimed ticket; failed attempts can retry."""
        ticket = self.store.claim(token)
        try:
            if ticket.replace:
                return {"status": "modified", **self.visible.ingest_bytes(ticket.name, data, replace=True)}
            return self.visible.upload(ticket.name or file_name, data)
        except BaseException:
            self.store.release(ticket)
            raise


class HiddenTrackService(TrackCollectionService):
    """The authenticated Hidden Vault: list, edit, delete, hide, and restore."""

    HIDDEN = True
    WRONG_COLLECTION_MESSAGE = "Only hidden tracks can use this route."

    def set_hidden(self, names: list[str], hidden: bool) -> dict[str, Any]:
        """Move tracks into or out of the logical Hidden Vault."""
        clean_names = unique_names(names, "Select at least one track.")
        for name in clean_names:
            self.storage.existing_path(name)
        changed = self.tracks.set_hidden(clean_names, hidden)
        return {
            "status": "hidden" if hidden else "restored",
            "names": changed,
            "count": len(changed),
        }

    def remove_many(self, names: list[str]) -> dict[str, Any]:
        clean_names = unique_names(names, "Select at least one hidden track.")
        for name in clean_names:
            self.remove(name)
        return {"status": "deleted", "count": len(clean_names)}


class SearchService:
    """Search visible tracks by meaning (CLAP) and by words, with optional tag and length filters."""

    def __init__(
        self, tracks: TrackRepository, rules: MetadataRules, encoder: ClapEncoder, limit_max: int
    ) -> None:
        self.tracks = tracks
        self.rules = rules
        self.encoder = encoder
        self.limit_max = limit_max

    def search(
        self,
        query: str,
        tags: list[str] | None,
        match_all_tags: bool,
        limit: int,
        offset: int,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Rank tracks for a description such as "upbeat piano for a morning run".

        The full query is embedded with CLAP, so tracks are found by how they
        sound even when no stored word matches; stored words still lift exact
        matches. Every visible track is ranked, best first, by ``score``.
        """
        text = query.strip()
        normalized_query = self.rules.search_query(query)
        normalized_tags = self.rules.normalize_tags(tags) if tags else []
        if not text and not normalized_tags:
            raise ValueError("Provide a description to search for or at least one tag.")
        limit, offset = min(max(limit, 1), self.limit_max), max(offset, 0)
        count, results = self.tracks.search(
            normalized_query,
            normalized_tags,
            match_all_tags,
            limit,
            offset,
            query_embedding=self.encoder.embed_text(text) if text else None,
            semantic_weight=AppConfig.SEMANTIC_WEIGHT,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )
        next_offset = offset + len(results)
        return {
            "query": query,
            "normalized_query": normalized_query,
            "count": count,
            "next_offset": next_offset if next_offset < count else None,
            "results": results,
        }


class PlaylistService:
    """Build a playlist that fits a description and fills a length, without repeating itself.

    Candidates come from a meaning search. Weak fits (well below the best
    match) are dropped, then tracks are picked one at a time by maximal
    marginal relevance: how well a track fits, minus how much it sounds like the
    tracks already picked. A near-copy of a picked track (such as a second
    generation from the same prompt) is held back until nothing else fits. The
    playlist is meant to loop; if the library holds less than the target length,
    it is shorter and says so.
    """

    CANDIDATES = 60
    # How far below the best match a track may score and still be a fit.
    FIT_MARGIN = 0.15
    # Relevance versus variety when picking the next track (1 = relevance only).
    RELEVANCE_WEIGHT = 0.7
    # Tracks this similar to one already picked count as near-copies.
    DUPLICATE_SIMILARITY = 0.98

    def __init__(self, search: SearchService, tracks: TrackRepository) -> None:
        self.search = search
        self.tracks = tracks

    def suggest(
        self,
        description: str,
        minutes: float = 45,
        tags: list[str] | None = None,
        min_track_seconds: float | None = None,
        max_track_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not description.strip():
            raise ValueError("Describe the music, for example \"calm acoustic for evening coffee\".")
        if not 1 <= minutes <= AppConfig.PLAYLIST_MAX_MINUTES:
            raise ValueError(f"minutes must be between 1 and {AppConfig.PLAYLIST_MAX_MINUTES}.")
        found = self.search.search(
            description, tags, False, self.CANDIDATES, 0, min_track_seconds, max_track_seconds
        )["results"]
        if not found:
            raise FileNotFoundError("No visible tracks match; store some tracks or relax the filters.")
        fits = [item for item in found if item["score"] >= found[0]["score"] - self.FIT_MARGIN]
        vectors = {name: np.asarray(vector) for name, vector in self.tracks.embeddings([i["name"] for i in fits]).items()}
        target, total, chosen = minutes * 60, 0.0, []
        pool = list(fits)
        def overlap(item: Row) -> float:
            vector = vectors.get(item["name"])
            if vector is None:
                return 0.0
            return max((float(vector @ vectors[p["name"]]) for p in chosen if p["name"] in vectors), default=0.0)

        while pool and total < target:
            fresh = [item for item in pool if overlap(item) < self.DUPLICATE_SIMILARITY] or pool
            best = max(
                fresh,
                key=lambda item: self.RELEVANCE_WEIGHT * item["score"] - (1 - self.RELEVANCE_WEIGHT) * overlap(item),
            )
            pool.remove(best)
            chosen.append(best)
            total += best["duration_seconds"] or 0
        return {
            "description": description,
            "target_minutes": minutes,
            "total_seconds": round(total, 1),
            "track_count": len(chosen),
            "loop": True,
            "note": None if total >= target else (
                f"Only {len(chosen)} fitting track(s), {round(total / 60, 1)} minutes; loop the playlist to fill the time."
            ),
            "tracks": [
                {
                    "position": position,
                    **{key: item[key] for key in ("name", "caption", "duration_seconds", "tempo_bpm",
                                                  "score", "cover_url", "public_url")},
                }
                for position, item in enumerate(chosen, start=1)
            ],
        }


class PlaybackService:
    """Play visible tracks on one of the host's speakers.

    With several speakers connected and none named, nothing plays: the caller
    gets the speaker list back so the user can choose.
    """

    def __init__(self, visible: VisibleTrackService, player: SpeakerPlayer, max_tracks: int) -> None:
        self.visible = visible
        self.player = player
        self.max_tracks = max_tracks

    def speakers(self) -> dict[str, Any]:
        speakers = self.player.speakers()
        return {"count": len(speakers), "speakers": [speaker.as_row() for speaker in speakers]}

    @staticmethod
    def match(speakers: list[Speaker], requested: str) -> Speaker:
        """Find a speaker by exact name, else by a unique case-insensitive partial name or description."""
        exact = [speaker for speaker in speakers if speaker.name == requested]
        query = requested.strip().lower()
        partial = [
            speaker
            for speaker in speakers
            if query and (query in speaker.name.lower() or query in speaker.description.lower())
        ]
        matches = exact or partial
        if len(matches) == 1:
            return matches[0]
        options = ", ".join(f"{speaker.name} ({speaker.description})" for speaker in speakers)
        problem = "matches several speakers" if matches else "matches no speaker"
        raise ValueError(f"Speaker {requested!r} {problem}. Available: {options}.")

    def play(self, names: list[str], speaker: str | None = None, loop: bool = False) -> dict[str, Any]:
        if isinstance(names, list) and any(not isinstance(name, str) for name in names):
            raise ValueError("Every track name must be a string.")
        clean_names = unique_names(names, "Provide at least one track name.")
        if len(clean_names) > self.max_tracks:
            raise ValueError(f"Play at most {self.max_tracks} tracks at a time.")
        queue = [(name, self.visible.path(name)) for name in clean_names]
        speakers = self.player.speakers()
        if speaker is not None:
            chosen = self.match(speakers, speaker)
        elif len(speakers) == 1:
            chosen = speakers[0]
        else:
            return {
                "status": "choose_speaker",
                "message": (
                    "Several speakers are connected. Ask the user which one to play on, then call "
                    "play_tracks again with speaker set to its name."
                ),
                "speakers": [option.as_row() for option in speakers],
            }
        current = self.player.status()
        if current["status"] == "playing" and current["tracks"] == clean_names and current["loop"] == loop:
            # The same queue on another speaker: carry on where it is instead of restarting.
            return self.player.switch(chosen)
        return self.player.play(queue, chosen, loop)

    def switch_speaker(self, speaker: str) -> dict[str, Any]:
        """Move what plays to ``speaker``, resuming the current track where it is."""
        return self.player.switch(self.match(self.player.speakers(), speaker))


class VibiaService:
    """Facade grouping every Luna Vibia use case for the transport adapters."""

    def __init__(
        self,
        visible: VisibleTrackService,
        hidden: HiddenTrackService,
        search: SearchService,
        playlists: PlaylistService,
        indexer: TrackIndexer,
        urls: PublicURLService,
        downloads: TrackDownloadService,
        uploads: UploadLinkService,
        playback: PlaybackService,
    ) -> None:
        self.visible = visible
        self.hidden = hidden
        self.search = search
        self.playlists = playlists
        self.indexer = indexer
        self.urls = urls
        self.downloads = downloads
        self.uploads = uploads
        self.playback = playback

    @classmethod
    def create(
        cls,
        config: AppConfig,
        tracks: TrackRepository,
        public_urls: PublicURLRepository,
        captioner: OllamaCaptioner,
        encoder: ClapEncoder,
        covers: VisiaImageCatalog,
        player: SpeakerPlayer | None = None,
    ) -> "VibiaService":
        """Wire the use cases around the given persistence and analysis adapters."""
        rules = MetadataRules(config.max_tags, config.search_stop_words)
        storage = TrackStorage(config.track_dir, set(config.allowed_formats))
        urls = PublicURLService(public_urls)
        urls.seed(config.public_base_url)
        inspector = TrackInspector()
        indexer = TrackIndexer(storage, tracks, captioner, encoder, urls, inspector, rules)
        visible = VisibleTrackService(
            storage,
            tracks,
            rules,
            TrackPayloadDecoder(config.allowed_formats, config.max_track_bytes),
            indexer,
            inspector,
            covers,
            config.max_fetch_tracks,
            config.max_fetch_bytes,
        )
        search = SearchService(tracks, rules, encoder, config.search_limit_max)
        return cls(
            visible=visible,
            hidden=HiddenTrackService(storage, tracks, rules, inspector),
            search=search,
            playlists=PlaylistService(search, tracks),
            indexer=indexer,
            urls=urls,
            downloads=TrackDownloadService(
                visible,
                DownloadStore(
                    config.download_dir,
                    config.download_ttl_seconds,
                    config.max_download_store_bytes,
                ),
                urls,
                config.max_archive_tracks,
                config.max_archive_bytes,
            ),
            uploads=UploadLinkService(
                visible, UploadLinkStore(config.upload_ttl_seconds), urls, config.max_track_bytes
            ),
            playback=PlaybackService(visible, player or SpeakerPlayer(), config.max_play_tracks),
        )
