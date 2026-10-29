"""Read-only access to vault track files, with cached cover art from Luna Visia."""

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httpx
import streamlit as st
from PIL import Image, ImageDraw, ImageOps

from services.api import LunaVibiaAPI
from config import UIConfig


class TrackFiles:
    """List vault files and render cached cover art and facts for them."""

    AUDIO_TYPES = {
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".wav": "audio/wav",
    }
    VISIA_IMAGE_PATH = re.compile(r"/api/public/images/[0-9a-fA-F-]{36}/?$")

    def __init__(self, config: UIConfig) -> None:
        self.config = config
        self.track_dir = config.track_dir
        self.track_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Path]:
        """List supported vault files newest first without decoding tracks."""
        return sorted(
            (
                path
                for path in self.track_dir.iterdir()
                if path.is_file() and path.suffix.lower() in self.config.track_extensions
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def path(self, name: str) -> Path:
        return self.track_dir / name

    @staticmethod
    @st.cache_data(show_spinner=False, max_entries=UIConfig.COVER_CACHE_ENTRIES, ttl=3600)
    def _cover(internal_url: str) -> bytes | None:
        """Fetch a cover from Luna Visia over the private network; None if it is gone."""
        try:
            response = httpx.get(internal_url, timeout=UIConfig.COVER_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError:
            return None

    def internal_cover_url(self, cover_url: str | None) -> str | None:
        """Turn a public Visia image URL into the same path on Visia's internal API."""
        match = self.VISIA_IMAGE_PATH.search(cover_url or "")
        return f"{self.config.visia_api_url}{match.group(0)}" if match else None

    @staticmethod
    @st.cache_data(show_spinner=False, max_entries=UIConfig.THUMBNAIL_CACHE_ENTRIES)
    def _placeholder(name: str, size: tuple[int, int]) -> Image.Image:
        """A gradient card with equalizer bars, coloured from the track's name."""
        digest = hashlib.sha256(name.encode()).digest()
        start, end = (digest[0], digest[1] // 2, 160 + digest[2] // 3), (40 + digest[3] // 3, 20, 70 + digest[4] // 4)
        width, height = size
        card = Image.new("RGB", size)
        draw = ImageDraw.Draw(card)
        for x in range(width):
            mix = x / max(width - 1, 1)
            draw.line([(x, 0), (x, height)], fill=tuple(int(a + (b - a) * mix) for a, b in zip(start, end)))
        bars, bar_width = 5, width // 24
        left = (width - (2 * bars - 1) * bar_width) // 2
        for index in range(bars):
            bar_height = int(height * (0.18 + 0.32 * digest[5 + index] / 255))
            x = left + index * 2 * bar_width
            draw.rounded_rectangle(
                [x, (height - bar_height) // 2, x + bar_width, (height + bar_height) // 2],
                radius=bar_width // 2,
                fill=(245, 245, 245),
            )
        return card

    def _cover_image(self, name: str, cover_url: str | None, size: tuple[int, int]) -> Image.Image:
        internal_url = self.internal_cover_url(cover_url)
        data = self._cover(internal_url) if internal_url else None
        if data:
            try:
                with Image.open(BytesIO(data)) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            except OSError:
                pass
        return self._placeholder(name, size)

    def thumbnail(self, path: Path, cover_url: str | None) -> Image.Image:
        """Return a card-sized cover for a track: its Visia image, or a placeholder."""
        return self._cover_image(path.name, cover_url, self.config.card_size)

    def cover(self, path: Path, cover_url: str | None) -> Image.Image:
        """Return a large 4.5:3 cover for the track dialog."""
        return self._cover_image(path.name, cover_url, (720, 480))

    @staticmethod
    def size(path: Path) -> int:
        return path.stat().st_size

    @classmethod
    def mime_type(cls, path: Path) -> str:
        return cls.AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream")

    @staticmethod
    def duration_label(seconds: float | None) -> str:
        if not seconds:
            return "–"
        minutes, second = divmod(int(round(seconds)), 60)
        return f"{minutes}:{second:02d}"

    @staticmethod
    def size_label(size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    @staticmethod
    def display_name(stored_name: str) -> str:
        """Remove the internal upload prefix from a user-facing filename."""
        prefix, separator, original_name = stored_name.partition("_")
        if (
            separator
            and len(prefix) == 32
            and all(character in "0123456789abcdef" for character in prefix.lower())
        ):
            return original_name
        return stored_name


@dataclass(frozen=True)
class TrackCollection:
    """Vault files that have metadata in one collection, keyed by filename."""

    tracks: list[Path]
    metadata_by_name: dict[str, dict]

    @classmethod
    def from_metadata(cls, files: TrackFiles, metadata: list[dict]) -> "TrackCollection":
        metadata_by_name = {item["name"]: item for item in metadata}
        return cls(
            [path for path in files.list() if path.name in metadata_by_name],
            metadata_by_name,
        )

    @classmethod
    def visible(cls, api: LunaVibiaAPI, files: TrackFiles) -> "TrackCollection":
        return cls.from_metadata(files, api.metadata())

    def only(self, names: set[str]) -> "TrackCollection":
        return TrackCollection(
            [path for path in self.tracks if path.name in names], self.metadata_by_name
        )

    def matching(self, query: str) -> "TrackCollection":
        """Keep tracks whose display name or any tag contains ``query``."""
        if not query:
            return self

        def matches(path: Path) -> bool:
            if query in TrackFiles.display_name(path.name).casefold():
                return True
            tags = (self.metadata_by_name.get(path.name) or {}).get("tags", [])
            return any(query in str(tag).casefold() for tag in tags)

        return TrackCollection(
            [path for path in self.tracks if matches(path)], self.metadata_by_name
        )
