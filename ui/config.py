"""Validated presentation and service settings for the Streamlit UI."""

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
    """Immutable UI layout and backend-connection settings."""

    UI_ROOT: ClassVar[Path] = Path(__file__).resolve().parent
    LOGO_PATH: ClassVar[Path] = UI_ROOT / "assets" / "lunavibia_logo.png"
    MAX_TAGS: ClassVar[int] = 32
    UPLOAD_TYPES: ClassVar[tuple[str, ...]] = ("mp3", "wav", "flac", "ogg", "opus", "m4a")
    API_TIMEOUT_SECONDS: ClassVar[float] = 30.0
    LIST_TIMEOUT_SECONDS: ClassVar[float] = 10.0
    # The playback line re-reads where sound goes; Windows can switch speakers on its own.
    PLAYBACK_REFRESH_SECONDS: ClassVar[int] = 10
    PLAYBACK_TIMEOUT_SECONDS: ClassVar[float] = 8.0
    # Uploads wait for the backend to listen to, measure, and caption the track.
    UPLOAD_TIMEOUT_SECONDS: ClassVar[float] = 360.0
    THUMBNAIL_CACHE_ENTRIES: ClassVar[int] = 256
    COVER_CACHE_ENTRIES: ClassVar[int] = 256
    COVER_TIMEOUT_SECONDS: ClassVar[float] = 5.0

    track_dir: Path
    api_url: str
    api_token: str
    allowed_emails: frozenset[str]
    sso: SSOConfig
    # Luna Visia's API on the private network, where cover art is fetched from.
    visia_api_url: str = "http://luna-visia-mcp:8000"
    card_size: tuple[int, int] = (420, 248)
    gallery_corner_radius: int = 10
    gallery_selection_color: str = "#D4D4D4"
    gallery_border_thickness: int = 4
    gallery_max_row_height: int = 240
    gallery_columns: int = 3
    tracks_per_page: int = 12
    track_extensions: frozenset[str] = frozenset({".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"})

    @classmethod
    def from_env(cls) -> "UIConfig":
        """Build and validate UI configuration from environment variables."""
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
        if not allowed_emails:
            raise RuntimeError("LUNAVIBIA_ALLOWED_EMAILS must list at least one account.")
        return cls(
            track_dir=Path(os.getenv("TRACK_DIR", "/data/tracks")),
            api_url=api_url,
            api_token=api_token,
            allowed_emails=allowed_emails,
            sso=SSOConfig.from_env(),
            visia_api_url=os.getenv("LUNAVISIA_API_URL", cls.visia_api_url).rstrip("/"),
        )
