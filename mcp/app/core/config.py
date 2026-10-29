"""Validated runtime configuration for the Luna Vibia backend."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse


@dataclass(frozen=True)
class AppConfig:
    """Immutable backend settings loaded from environment variables."""

    ASSET_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent / "assets"
    # Every Luna app asks Sentia's Ollama for this context. Ollama reloads a model
    # whose requested context changes, so matching it lets the apps share one
    # loaded copy instead of swapping it (about 6 s) whenever they alternate.
    CAPTION_CONTEXT_TOKENS: ClassVar[int] = 16_384
    CAPTION_TIMEOUT_SECONDS: ClassVar[float] = 300.0
    CAPTION_CONNECT_TIMEOUT_SECONDS: ClassVar[float] = 10.0
    REMOTE_FETCH_TIMEOUT_SECONDS: ClassVar[float] = 30.0
    VISIA_TIMEOUT_SECONDS: ClassVar[float] = 10.0
    # ffprobe and ffmpeg on one file; a long file still decodes in seconds.
    AUDIO_TOOL_TIMEOUT_SECONDS: ClassVar[int] = 120
    # Listing the host's speakers asks its sound server; stopping waits for ffmpeg to exit.
    SPEAKER_LIST_TIMEOUT_SECONDS: ClassVar[int] = 10
    # The Windows speaker helper asks PowerShell, which takes about 5 s per listing.
    SPEAKER_HELPER_TIMEOUT_SECONDS: ClassVar[float] = 30.0
    # Reading only the current output takes about a second.
    SPEAKER_OUTPUT_TIMEOUT_SECONDS: ClassVar[float] = 10.0
    PLAYBACK_STOP_TIMEOUT_SECONDS: ClassVar[int] = 5
    # CLAP hears 10-second, 48 kHz clips; a track is heard as up to this many clips
    # spread over its length, and their embeddings are averaged. The music-only
    # laion/larger_clap_music checkpoint scores every description near zero under
    # Transformers, so the general (music and sound) checkpoint is used.
    CLAP_MODEL: ClassVar[str] = "laion/clap-htsat-unfused"
    CLAP_SAMPLE_RATE: ClassVar[int] = 48_000
    CLAP_CLIP_SECONDS: ClassVar[int] = 10
    CLAP_MAX_CLIPS: ClassVar[int] = 6
    CLAP_DEVICES: ClassVar[frozenset[str]] = frozenset({"auto", "cuda", "cpu"})
    # A CLAP call that finds the GPU full waits for Docling to finish its document and
    # move aside, trying this many times (1 s, then 2 s, ... apart) before using the CPU.
    CLAP_GPU_ATTEMPTS: ClassVar[int] = 3
    CLAP_GPU_RETRY_SECONDS: ClassVar[float] = 1.0
    # Tempo, key, and energy are measured on this much audio from the middle of a track.
    FEATURE_SAMPLE_RATE: ClassVar[int] = 22_050
    FEATURE_MAX_SECONDS: ClassVar[int] = 120
    # Longest embedded text (generator prompts, comments) kept from a file's tags.
    INSPECTION_MAX_TEXT_CHARS: ClassVar[int] = 1000
    # Search ranks by meaning (CLAP) and by words (full text); this weights meaning.
    SEMANTIC_WEIGHT: ClassVar[float] = 0.75
    # Leftover archives without a ticket are only removed once clearly abandoned, so a
    # concurrent purge never deletes an archive whose ticket is being written.
    DOWNLOAD_LEFTOVER_GRACE_SECONDS: ClassVar[int] = 60 * 60
    FULL_DETAIL_MAX_TRACKS: ClassVar[int] = 20
    BATCH_MAX_TRACKS: ClassVar[int] = 100
    PLAYLIST_MAX_MINUTES: ClassVar[int] = 360
    CREDENTIAL_SALT_BYTES: ClassVar[int] = 16

    track_dir: Path
    database_url: str
    ollama_url: str
    caption_model: str
    visia_api_url: str = "http://luna-visia-mcp:8000"
    # Visia image ID of the audio placeholder covering tracks no Visia image suits ("" = none yet).
    placeholder_cover_id: str = ""
    public_base_url: str = ""
    api_token: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_formats: dict[str, str] = field(
        default_factory=lambda: {
            ".flac": "FLAC",
            ".m4a": "M4A",
            ".mp3": "MP3",
            ".ogg": "OGG",
            ".opus": "OGG",
            ".wav": "WAV",
        }
    )
    max_track_bytes: int = 200 * 1024 * 1024
    max_fetch_tracks: int = 20
    max_fetch_bytes: int = 200 * 1024 * 1024
    max_upload_redirects: int = 3
    # ZIPs are served as download links, so they are not bound by MCP message size.
    max_archive_tracks: int = 200
    max_archive_bytes: int = 4 * 1024 * 1024 * 1024
    # Files play from disk on the host's speakers, so only the queue length is bounded.
    max_play_tracks: int = 200
    download_ttl_seconds: int = 24 * 60 * 60
    max_download_store_bytes: int = 20 * 1024 * 1024 * 1024
    upload_ttl_seconds: int = 15 * 60
    # A persistent volume, so download links keep working across restarts.
    download_dir: Path = Path("/data/downloads")
    max_tags: int = 32
    search_limit_max: int = 100
    password_hash_iterations: int = 600_000
    hidden_session_seconds: int = 30 * 60
    search_stop_words: frozenset[str] = frozenset(
        {
            "about",
            "all",
            "are",
            "audio",
            "count",
            "do",
            "find",
            "how",
            "many",
            "music",
            "of",
            "play",
            "show",
            "something",
            "song",
            "songs",
            "that",
            "the",
            "there",
            "track",
            "tracks",
            "what",
            "with",
        }
    )
    # Public HTTPS origin of this MCP server, used for icon URLs ("" = embedded icons only).
    mcp_public_url: str = ""
    # The WSL host's Windows speaker helper ("" = list the PulseAudio sinks directly).
    speaker_helper_url: str = ""
    # Where CLAP runs: auto uses a CUDA GPU when present.
    clap_device: str = "auto"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build and validate backend configuration from the environment."""
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required.")
        ollama_url = os.getenv("OLLAMA_URL", "http://luna-sentia-ollama:11434").rstrip("/")
        parsed = urlparse(ollama_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("OLLAMA_URL must be a valid HTTP(S) URL.")
        caption_model = os.getenv("CAPTION_MODEL", "qwen3-vl:8b-instruct").strip()
        if not caption_model:
            raise RuntimeError("CAPTION_MODEL cannot be blank.")
        visia_api_url = os.getenv("LUNAVISIA_API_URL", cls.visia_api_url).strip().rstrip("/")
        parsed = urlparse(visia_api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNAVISIA_API_URL must be a valid HTTP(S) URL.")
        placeholder_cover_id = os.getenv("LUNAVIBIA_PLACEHOLDER_COVER_ID", "").strip().lower()
        if placeholder_cover_id and not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", placeholder_cover_id
        ):
            raise RuntimeError("LUNAVIBIA_PLACEHOLDER_COVER_ID must be a Luna Visia image ID (a UUID).")
        track_dir = Path(os.getenv("TRACK_DIR", "/data/tracks"))
        public_base_url = os.getenv("LUNAVIBIA_PUBLIC_BASE_URL", "").strip().rstrip("/")
        if public_base_url:
            public_url = urlparse(public_base_url)
            if public_url.scheme != "https" or not public_url.netloc:
                raise RuntimeError("LUNAVIBIA_PUBLIC_BASE_URL must be a valid HTTPS URL.")
        api_token = os.getenv("LUNAVIBIA_API_TOKEN", "").strip()
        if len(api_token) < 32:
            raise RuntimeError("LUNAVIBIA_API_TOKEN must contain at least 32 characters.")
        mcp_public_url = os.getenv("MCP_PUBLIC_URL", "").strip().rstrip("/")
        if mcp_public_url:
            parsed_public_url = urlparse(mcp_public_url)
            local = parsed_public_url.scheme == "http" and parsed_public_url.hostname in {"localhost", "127.0.0.1"}
            if not parsed_public_url.netloc or (parsed_public_url.scheme != "https" and not local):
                raise RuntimeError("MCP_PUBLIC_URL must be an HTTPS URL (plain HTTP only on localhost).")
        speaker_helper_url = os.getenv("LUNAVIBIA_SPEAKER_HELPER_URL", "").strip().rstrip("/")
        if speaker_helper_url:
            parsed_helper_url = urlparse(speaker_helper_url)
            if parsed_helper_url.scheme not in {"http", "https"} or not parsed_helper_url.netloc:
                raise RuntimeError("LUNAVIBIA_SPEAKER_HELPER_URL must be a valid HTTP(S) URL.")
        clap_device = os.getenv("CLAP_DEVICE", "auto").strip().lower()
        if clap_device not in cls.CLAP_DEVICES:
            raise RuntimeError(f"CLAP_DEVICE must be one of: {', '.join(sorted(cls.CLAP_DEVICES))}.")
        return cls(
            clap_device=clap_device,
            speaker_helper_url=speaker_helper_url,
            mcp_public_url=mcp_public_url,
            track_dir=track_dir,
            database_url=database_url,
            ollama_url=ollama_url,
            caption_model=caption_model,
            visia_api_url=visia_api_url,
            placeholder_cover_id=placeholder_cover_id,
            public_base_url=public_base_url,
            api_token=api_token,
        )
