"""MCP tools that let LLM clients manage Luna Vibia tracks."""

from collections.abc import Callable
from typing import Annotated, Any, Literal, TypeVar

import anyio
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, WithJsonSchema

from app.core.models import MetadataChange, MetadataRules
from app.integrations.remote import TrackSourceResolver
from app.services.application import VibiaService

Result = TypeVar("Result")

# ChatGPT passes attachments to parameters listed here as {download_url, file_id}.
FILE_PARAMS_META = {"openai/fileParams": ["file"]}


class FileReference(BaseModel):
    """A client-hosted attachment, as passed by ChatGPT for file parameters."""

    model_config = ConfigDict(extra="allow")

    download_url: str
    file_id: str | None = None


# Inline (no $ref) so every LLM client can read the parameter shape.
FileInput = Annotated[
    FileReference | None,
    WithJsonSchema(
        {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "download_url": {"type": "string"},
                        "file_id": {"type": "string"},
                    },
                    "required": ["download_url"],
                },
                {"type": "null"},
            ],
            "description": "An attached audio file passed by the chat client.",
        }
    ),
]


class MetadataUpdate(BaseModel):
    """One track's caption and tag change within a batch."""

    name: str
    caption: str | None = None
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None


class RenameRequest(BaseModel):
    """One track rename within a batch."""

    name: str
    new_name: str


TAG_LIST_SCHEMA = {"type": "array", "items": {"type": "string"}}

MetadataUpdates = Annotated[
    list[MetadataUpdate],
    WithJsonSchema(
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "caption": {"type": "string"},
                    "add_tags": TAG_LIST_SCHEMA,
                    "remove_tags": TAG_LIST_SCHEMA,
                },
                "required": ["name"],
            },
            "description": "One entry per track: its exact name and the changes to apply.",
        }
    ),
]

RenameRequests = Annotated[
    list[RenameRequest],
    WithJsonSchema(
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "new_name": {"type": "string"}},
                "required": ["name", "new_name"],
            },
            "description": "One entry per track: its exact current name and the new name.",
        }
    ),
]


async def offload(function: Callable[..., Result], *args: Any) -> Result:
    """Run slow, blocking work (audio analysis, archives) off the event loop.

    FastMCP calls synchronous tools on the event loop, so a blocking tool would
    stall every other request, including the web UI and health checks.
    """
    return await anyio.to_thread.run_sync(function, *args)


class VibiaMCPTools:
    """Register Luna Vibia's MCP tool surface on a FastMCP server.

    Hidden tracks are never reachable through these public tools.
    """

    def __init__(
        self,
        server: FastMCP,
        service: VibiaService,
        sources: TrackSourceResolver,
    ) -> None:
        self.server = server
        self.service = service
        self.sources = sources
        self._register_library_tools()
        self._register_delivery_tools()
        self._register_playback_tools()
        self._register_mutation_tools()

    def _register_library_tools(self) -> None:
        server, visible, search, playlists, indexer = (
            self.server,
            self.service.visible,
            self.service.search,
            self.service.playlists,
            self.service.indexer,
        )

        @server.tool()
        def list_tracks(limit: int = 50, offset: int = 0) -> dict[str, Any]:
            """List visible tracks newest first, one page at a time.

            Each track has its exact name, caption, tags, favorite flag, title,
            artist, duration, tempo, key, energy, cover_url (a Luna Visia image or
            null), and public_url (a playable link). Follow next_offset for the
            next page (it is null on the last page).
            """
            return visible.list_page(limit, offset, self.service.search.limit_max)

        @server.tool()
        async def search_tracks(
            query: str = "",
            tags: list[str] | None = None,
            match_all_tags: bool = False,
            min_seconds: float | None = None,
            max_seconds: float | None = None,
            limit: int = 20,
            offset: int = 0,
        ) -> dict[str, Any]:
            """Find tracks by how they sound, described in plain words.

            query is a description such as "calm acoustic for evening coffee" or
            "upbeat electronic for a run". It is matched by meaning against the
            sound of every track (a music-text embedding), and stored words lift
            exact matches, so results are ranked best first by score. Optional
            tags (lowercase) and min_seconds/max_seconds narrow the results.
            Each result has a playable public_url and its cover_url.
            """
            MetadataRules.require_lowercase_tags(tags, "tags")
            return await offload(
                search.search, query, tags, match_all_tags, limit, offset, min_seconds, max_seconds
            )

        @server.tool()
        async def suggest_playlist(
            description: str,
            minutes: float = 45,
            tags: list[str] | None = None,
            min_track_seconds: float | None = None,
            max_track_seconds: float | None = None,
        ) -> dict[str, Any]:
            """Build a looping playlist that fits a mood or moment, such as "evening coffee vibes".

            Picks tracks that match the description by sound, drops weak fits, and
            orders them to fill about `minutes` while avoiding tracks that sound
            alike. Returns the tracks in play order with public_url and cover_url.
            If the library holds less fitting music than requested, the playlist
            is shorter and the note says to loop it.
            """
            MetadataRules.require_lowercase_tags(tags, "tags")
            return await offload(
                playlists.suggest, description, minutes, tags, min_track_seconds, max_track_seconds
            )

        @server.tool()
        async def get_track_metadata(name: str) -> dict[str, Any]:
            """Return all metadata for one visible track: stored, measured, and embedded.

            Includes the caption, tags, favorite flag, title, artist, generator
            notes, duration, tempo, key, energy, cover_url, size, SHA-256, analysis
            model, timestamps, and public_url, plus what the file itself carries:
            format, codec, sample rate, channels, bitrate, and its text tags
            (embedded_tags).
            ai_generated and ai_signals say whether the tags name an AI music
            generator (such tracks carry the "ai info" tag); missing signals do
            not prove a track is human-made, since re-encoding drops tags.
            """
            return await offload(visible.metadata, name)

        @server.tool()
        async def list_track_metadata(
            limit: int = 50,
            offset: int = 0,
            names: list[str] | None = None,
            detail: Literal["summary", "full"] = "summary",
        ) -> dict[str, Any]:
            """Return metadata for many visible tracks at once, for bulk review and classification.

            Pages newest first like list_tracks (follow next_offset; null on the
            last page), or pass names for an exact batch; missing or hidden names
            are listed under "unavailable".
            - summary (up to 100 per call): the list_tracks fields plus an
              "embedded" object with format, duration, ai_generated, ai_signals,
              generator, title, and artist from the file.
            - full (up to 20 per call): the complete get_track_metadata output
              for each track.
            """
            return await offload(
                visible.metadata_page, limit, offset, search.limit_max, names, detail
            )

        @server.tool()
        async def get_library_stats(top_tags: int = 10) -> dict[str, Any]:
            """Return statistics for the visible library, computed from stored metadata.

            Includes total_tracks, favorite_count, with_cover_count,
            ai_generated_count (tracks whose tags name an AI generator),
            ai_modified_count (tracks replaced via modify_track), total listening
            time, total and average size, the largest track, a count per audio
            format, unique_tag_count, the top_tags most used tags, and the oldest
            and newest updated_at. Hidden tracks are not counted.
            """
            return await offload(visible.stats, top_tags)

        @server.tool()
        async def backfill_metadata() -> dict[str, Any]:
            """Analyze files missing current metadata; idempotent by hash and models.

            Also adds the "ai info" tag to already-indexed AI-generated tracks.
            """
            return await offload(indexer.backfill)

    def _register_delivery_tools(self) -> None:
        server, visible, urls, downloads = (
            self.server,
            self.service.visible,
            self.service.urls,
            self.service.downloads,
        )

        @server.tool()
        def get_track_url(name: str) -> dict[str, str]:
            """Return the public, playable HTTPS URL for one non-hidden stored track."""
            return {"name": name, "url": visible.public_url(name)}

        @server.tool()
        def set_public_base_url(public_base_url: str) -> dict[str, Any]:
            """Change the public HTTPS origin used by all Luna Vibia track URLs.

            Supply the full externally reachable base, including any path prefix,
            for example https://vibia.example.com. Every stored track URL is
            regenerated immediately; no service restart is required.
            """
            return urls.update(public_base_url)

        @server.tool()
        async def download_tracks(names: list[str]) -> dict[str, Any]:
            """Package visible tracks' original files as a downloadable ZIP.

            Use exact filenames returned by list_tracks or search_tracks (at most
            200 tracks, 4 GiB). Give the user download_url exactly as returned; it
            expires at expires_at (24 hours). To play a single track, give its
            public_url instead.
            """
            return await offload(downloads.create_zip, names)

    def _register_playback_tools(self) -> None:
        server, playback = self.server, self.service.playback

        @server.tool()
        async def list_speakers() -> dict[str, Any]:
            """List the speakers (audio outputs) connected to the machine running Luna Vibia.

            Each has a name to pass to play_tracks, a description to show the
            user, and default (the output the host uses by default).
            """
            return await offload(playback.speakers)

        @server.tool()
        async def play_tracks(
            names: list[str], speaker: str | None = None, loop: bool = False
        ) -> dict[str, Any]:
            """Play visible tracks out loud on the host machine's speakers, in the given order.

            Use exact names from list_tracks, search_tracks, or suggest_playlist
            (at most 200); set loop=true to repeat the queue, as suggest_playlist
            advises. Starting a new queue stops the current one.

            speaker is a name or description from list_speakers. If it is omitted
            and only one speaker is connected, that one plays. If several are
            connected, nothing plays: the result has status "choose_speaker" and
            the options; ask the user which one, then call again with speaker.
            """
            return await offload(playback.play, names, speaker, loop)

        @server.tool()
        async def stop_playback() -> dict[str, Any]:
            """Stop whatever play_tracks is playing on the host's speakers."""
            return await offload(playback.player.stop)

        @server.tool()
        def get_playback_status() -> dict[str, Any]:
            """Return what is playing: status, speaker, queued tracks, loop, and now_playing.

            status is idle, playing, finished, or failed (with the track and error).
            """
            return playback.player.status()

    def _register_mutation_tools(self) -> None:
        server, visible, sources, uploads = (
            self.server,
            self.service.visible,
            self.sources,
            self.service.uploads,
        )

        def upload(name, base64_data, track_url, file, title, artist, notes, cover_url):
            source = sources.resolve(base64_data, track_url, file.model_dump() if file else None)
            given = {"title": title, "artist": artist, "notes": notes}
            return visible.upload_with_cover(name or source.suggested_name, source.data, given, cover_url)

        @server.tool(meta=FILE_PARAMS_META)
        async def upload_track(
            name: str | None = None,
            file: FileInput = None,
            track_url: str | None = None,
            content_base64: str | None = None,
            title: str | None = None,
            artist: str | None = None,
            notes: str | None = None,
            cover_url: str | None = None,
        ) -> dict[str, Any]:
            """Add a music track (MP3, WAV, FLAC, OGG/Opus, M4A); it is analyzed and captioned.

            Provide exactly one source:
            - file: an audio file the user attached in chat (ChatGPT supplies it).
            - track_url: a public HTTPS audio URL or an audio data URL.
            - content_base64: Base64 audio bytes; only practical for short clips.
            To upload a local file from a shell or code sandbox, use
            create_upload_link instead of Base64.

            When you generated the music, pass the prompt or style you used as
            notes (and title/artist if any): it is stored with the track and
            sharpens its caption and tags.

            Always search Luna Visia for cover art that suits the track (its mood,
            genre, or title) before uploading, and pass the public_url it returns
            as cover_url (an immutable .../api/public/images/<image-id> URL). If
            that search finds no suitable image, omit cover_url: the track then
            gets the Luna Vibia audio placeholder stored in Visia. Never invent a
            URL or pass a filename-based URL or data URI; a supplied URL is checked
            against Luna Visia and the upload is rejected if it is not found.

            name is optional. The extension is corrected to match the audio
            format, a taken name gets a numeric suffix, and an exact duplicate of a
            stored track returns status "duplicate" instead of a second copy.
            Maximum size: 200 MiB. Analysis takes about half a minute.
            """
            return await offload(upload, name, content_base64, track_url, file, title, artist, notes, cover_url)

        @server.tool()
        def create_upload_link(name: str, replace: bool = False) -> dict[str, Any]:
            """Create a single-use HTTPS link for uploading a local audio file.

            Use this when you can run commands (a shell or code sandbox) and have
            the track as a file: POST its bytes to upload_url, for example with the
            returned curl_example. The link expires after 15 minutes. With
            replace=true, name must be an existing visible track to overwrite.
            After a new upload, give it a cover with set_track_cover: search Luna
            Visia first, and omit cover_url for the audio placeholder if none fits.
            """
            return uploads.create_link(name, replace)

        @server.tool(meta=FILE_PARAMS_META)
        async def modify_track(
            name: str,
            content_base64: str | None = None,
            track_url: str | None = None,
            file: FileInput = None,
        ) -> dict[str, Any]:
            """Analyze and atomically replace a non-hidden track's audio and metadata.

            Provide exactly one of file, track_url, or content_base64; the new audio
            must have the same format as the existing file's extension. The title,
            artist, notes, and cover are kept.
            """

            def replace() -> dict[str, Any]:
                source = sources.resolve(content_base64, track_url, file.model_dump() if file else None)
                return {"status": "modified", **visible.ingest_bytes(name, source.data, replace=True)}

            return await offload(replace)

        @server.tool()
        async def set_track_cover(name: str, cover_url: str | None = None) -> dict[str, Any]:
            """Set a track's cover art to a Luna Visia image, or to the audio placeholder.

            Always search Luna Visia first for an image that suits the track (its
            mood, genre, or title), then pass the public_url Visia returns: an
            immutable .../api/public/images/<image-id> URL. It is checked against
            Luna Visia and rejected if the image is missing or hidden. If no image
            fits, omit cover_url: the track then shows the Luna Vibia audio
            placeholder stored in Visia. Never pass a filename-based URL or data URI.
            """
            return {"status": "cover_updated", **await offload(visible.set_cover, name, cover_url, True)}

        @server.tool()
        def update_track_metadata(
            name: str,
            caption: str | None = None,
            add_tags: list[str] | None = None,
            remove_tags: list[str] | None = None,
        ) -> dict[str, Any]:
            """Edit a visible track's caption and add or remove searchable tags.

            Tags must be lowercase; a tag containing capital letters is rejected
            and nothing is changed. The "ai info" tag cannot be removed from
            tracks whose embedded tags name an AI music generator.
            """
            MetadataRules.require_lowercase_tags(add_tags, "add_tags")
            MetadataRules.require_lowercase_tags(remove_tags, "remove_tags")
            change = MetadataChange(caption, add_tags, remove_tags)
            return {"status": "metadata_updated", **visible.update_metadata(name, change)}

        @server.tool()
        async def update_tracks_metadata(updates: MetadataUpdates) -> dict[str, Any]:
            """Edit captions and add or remove tags on up to 100 visible tracks at once.

            Each entry is applied independently: successes are listed under
            "updated" and per-track errors under "failed" (for example a missing
            name, too many tags, or removing "ai info" from an AI-generated track).
            Tags must be lowercase; any capitalized tag rejects the whole batch
            and nothing is changed.
            """
            for update in updates:
                MetadataRules.require_lowercase_tags(update.add_tags, f"add_tags for {update.name!r}")
                MetadataRules.require_lowercase_tags(update.remove_tags, f"remove_tags for {update.name!r}")
            changes = [
                (update.name, MetadataChange(update.caption, update.add_tags, update.remove_tags))
                for update in updates
            ]
            return {"status": "metadata_updated", **await offload(visible.update_metadata_many, changes)}

        @server.tool()
        async def rename_tracks(renames: RenameRequests) -> dict[str, Any]:
            """Rename up to 100 visible tracks at once, applied in the given order.

            The same rules as rename_track apply to each: only letters, numbers,
            and underscores, the extension unchanged, and the immutable ID and
            public URL kept. Each rename is independent: successes are listed
            under "renamed" and per-track errors under "failed".
            """
            pairs = [(rename.name, rename.new_name) for rename in renames]
            return {"status": "renamed", **await offload(visible.rename_many, pairs)}

        @server.tool()
        def rename_track(name: str, new_name: str) -> dict[str, Any]:
            """Rename a track using only letters, numbers, and underscores.

            Keep the existing file extension. Spaces, hyphens, and other special
            characters are not allowed. The immutable ID and public URL remain
            unchanged.
            """
            return visible.rename(name, new_name)

        @server.tool()
        def set_favorite_tracks(names: list[str], favorite: bool) -> dict[str, Any]:
            """Add or remove visible tracks from Favorites.

            Use exact filenames returned by list_tracks or search_tracks. Set
            favorite to true to add the tracks or false to remove them.
            """
            return visible.set_favorite(names, favorite)

        @server.tool()
        def remove_track(name: str) -> dict[str, str]:
            """Remove a non-hidden track and its persisted metadata consistently."""
            return visible.remove(name)
