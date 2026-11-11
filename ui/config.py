"""Validated settings for the UI gateway and the browser app it serves."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse


@dataclass(frozen=True)
class SSOConfig:
    """Single sign-on through Luna Sentia; this block is identical in every Luna app's config.py."""

    COOKIE_NAME: ClassVar[str] = "luna_sso"
    SESSION_HEADER: ClassVar[str] = "X-Luna-Session"
    # How long a confirmed session is trusted before asking Sentia again, so a sign-out
    # in another app takes effect here within this many seconds.
    RECHECK_SECONDS: ClassVar[int] = 60
    LOOKUP_TIMEOUT_SECONDS: ClassVar[float] = 5.0
    SESSION_CACHE_ENTRIES: ClassVar[int] = 256

    public_url: str
    internal_url: str = "http://luna-sentia-auth:8000"

    @classmethod
    def from_env(cls) -> "SSOConfig":
        public_url = os.getenv("LUNA_SSO_URL", "").strip().rstrip("/")
        if not public_url:
            raise RuntimeError("LUNA_SSO_URL must be the public address of Luna Sentia's auth service.")
        internal_url = os.getenv("LUNA_SSO_INTERNAL_URL", "").strip().rstrip("/")
        return cls(public_url=public_url, internal_url=internal_url or cls.internal_url)


@dataclass(frozen=True)
class UIConfig:
    """Immutable gateway settings, plus what the browser app reads from ``/auth/session``."""

    UI_ROOT: ClassVar[Path] = Path(__file__).resolve().parent
    # The release this image holds, shown in the footer and on Luna Unia's cards.
    VERSION: ClassVar[str] = os.getenv("LUNA_VERSION", "").strip()
    # The built React app; the Dockerfile puts it here.
    STATIC_DIR: ClassVar[Path] = UI_ROOT / "static"
    MAX_TAGS: ClassVar[int] = 32
    NAME_MAX_CHARS: ClassVar[int] = 200
    CAPTION_MAX_CHARS: ClassVar[int] = 500
    TRACKS_PER_PAGE: ClassVar[int] = 12
    # A bulk action is sent in batches of this many tracks; the backend accepts up to 100.
    BATCH_SIZE: ClassVar[int] = 100
    UPLOAD_TYPES: ClassVar[tuple[str, ...]] = ("mp3", "wav", "flac", "ogg", "opus", "m4a")
    AUDIO_TYPES: ClassVar[dict[str, str]] = {
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".wav": "audio/wav",
    }
    API_TIMEOUT_SECONDS: ClassVar[float] = 30.0
    # A batch touches up to BATCH_SIZE tracks' files and records.
    BATCH_TIMEOUT_SECONDS: ClassVar[float] = 120.0
    # The playback line re-reads where sound goes; Windows can switch speakers on its own.
    PLAYBACK_REFRESH_SECONDS: ClassVar[int] = 10
    PLAYBACK_TIMEOUT_SECONDS: ClassVar[float] = 8.0
    # Uploads wait for the backend to listen to, measure, and caption the track.
    UPLOAD_TIMEOUT_SECONDS: ClassVar[float] = 360.0
    # A 200 MiB track grows by a third as base64, plus its JSON wrapper.
    MAX_REQUEST_BYTES: ClassVar[int] = 270 * 1024 * 1024
    # Twice the 420 x 280 card, and the player's cover, both 3:2.
    # Changing the shape also needs a new `shape` in the web app's coverUrl.
    COVER_SIZES: ClassVar[dict[str, tuple[int, int]]] = {"card": (840, 560), "large": (720, 480)}
    COVER_QUALITY: ClassVar[int] = 80
    COVER_CACHE_ENTRIES: ClassVar[int] = 256
    COVER_TIMEOUT_SECONDS: ClassVar[float] = 5.0
    # Cover and file URLs carry what they show, so they never go stale.
    IMMUTABLE_CACHE_CONTROL: ClassVar[str] = "private, max-age=31536000, immutable"
    # A cover Luna Visia could not give just now is asked for again soon.
    RETRY_CACHE_CONTROL: ClassVar[str] = "private, max-age=60"
    CONTENT_SECURITY_POLICY: ClassVar[str] = (
        "default-src 'self'; img-src 'self' data:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )

    track_dir: Path
    api_url: str
    api_token: str
    allowed_emails: frozenset[str]
    sso: SSOConfig
    # Luna Visia's API on the private network, where cover art is fetched from.
    visia_api_url: str = "http://luna-visia-mcp:8000"

    @classmethod
    def from_env(cls) -> "UIConfig":
        """Build and validate gateway configuration from environment variables."""
        api_url = (
            os.getenv("LUNAVIBIA_API_URL")
            or os.getenv("LUNAVAULT_API_URL")
            or "http://luna-vibia-mcp:8000"
        ).rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("LUNAVIBIA_API_URL must be a valid HTTP(S) URL.")
        api_token = os.getenv("LUNAVIBIA_API_TOKEN", "").strip()
        if len(api_token) < 32:
            raise RuntimeError("LUNAVIBIA_API_TOKEN must contain at least 32 characters.")
        allowed_emails = frozenset(
            email.strip().casefold()
            for email in os.getenv("LUNAVIBIA_ALLOWED_EMAILS", "").split(",")
            if email.strip()
        )
        return cls(
            track_dir=Path(os.getenv("TRACK_DIR", "/data/tracks")),
            api_url=api_url,
            api_token=api_token,
            allowed_emails=allowed_emails,
            sso=SSOConfig.from_env(),
            visia_api_url=os.getenv("LUNAVISIA_API_URL", cls.visia_api_url).rstrip("/"),
        )
