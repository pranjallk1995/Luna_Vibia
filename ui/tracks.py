"""Read-only access to vault track files, and cover art for them."""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from config import UIConfig

VISIA_IMAGE_PATH = re.compile(r"/api/public/images/[0-9a-fA-F-]{36}/?$")


class TrackFiles:
    """Pair backend metadata with the vault's files, and encode covers once."""

    def __init__(self, track_dir: Path) -> None:
        self.track_dir = track_dir
        self.covers: OrderedDict[tuple[str, str | None, str], bytes] = OrderedDict()

    def path(self, name: str) -> Path:
        """The vault file called ``name``; FileNotFoundError for anything else."""
        path = self.track_dir / name
        if Path(name).name != name or path.suffix.lower() not in UIConfig.AUDIO_TYPES or not path.is_file():
            raise FileNotFoundError(name)
        return path

    @staticmethod
    def media_type(path: Path) -> str:
        return UIConfig.AUDIO_TYPES[path.suffix.lower()]

    def collection(self, metadata: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Records with files on disk, newest first."""
        records = []
        for item in metadata:
            try:
                stat = self.path(item["name"]).stat()
            except OSError:
                continue
            records.append({**item, "size_bytes": stat.st_size, "version": stat.st_mtime_ns})
        records.sort(key=lambda record: record["version"], reverse=True)
        return records

    # Covers

    @staticmethod
    def visia_image_path(cover_url: str | None) -> str | None:
        """The path of a public Visia image link on Visia's internal API; None for anything else."""
        match = VISIA_IMAGE_PATH.search(cover_url or "")
        return match.group(0) if match else None

    @staticmethod
    def placeholder(name: str, size: tuple[int, int]) -> Image.Image:
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

    def cached_cover(self, name: str, cover_url: str | None, size: str) -> bytes | None:
        key = (name, cover_url, size)
        cached = self.covers.get(key)
        if cached is not None:
            self.covers.move_to_end(key)
        return cached

    def render_cover(self, name: str, cover_url: str | None, size: str, source: bytes | None) -> bytes:
        """Encode ``source``, or the placeholder; only a settled answer is kept, not a missing cover."""
        dimensions = UIConfig.COVER_SIZES[size]
        image = None
        if source:
            try:
                with Image.open(BytesIO(source)) as opened:
                    upright = ImageOps.exif_transpose(opened).convert("RGB")
                    image = ImageOps.fit(upright, dimensions, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            except OSError:
                image = None
        settled = image is not None or not cover_url
        encoded = BytesIO()
        (image or self.placeholder(name, dimensions)).save(encoded, "WEBP", quality=UIConfig.COVER_QUALITY)
        data = encoded.getvalue()
        if settled:
            key = (name, cover_url, size)
            self.covers[key] = data
            self.covers.move_to_end(key)
            while len(self.covers) > UIConfig.COVER_CACHE_ENTRIES:
                self.covers.popitem(last=False)
        return data
