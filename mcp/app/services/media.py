"""Audio byte validation, naming, and ZIP archives."""

import base64
import binascii
import re
import zipfile
from pathlib import Path

from app.integrations.audio import AudioProbe, AudioToolError


class TrackPayloadDecoder:
    """Decode track payloads, detect their real format, and check filenames.

    Base64 from LLM clients is often line-wrapped, unpadded, URL-safe, or a
    ``data:`` URL, so all of those are normalized before decoding. The format
    is what ffprobe finds in the bytes, never what the filename claims.
    """

    FORMAT_EXTENSIONS = {"FLAC": ".flac", "M4A": ".m4a", "MP3": ".mp3", "OGG": ".ogg", "WAV": ".wav"}
    DEFAULT_STEM = "track"

    def __init__(self, allowed_formats: dict[str, str], max_track_bytes: int, probe: AudioProbe | None = None) -> None:
        self.allowed_formats = allowed_formats
        self.max_track_bytes = max_track_bytes
        self.probe = probe or AudioProbe()

    @property
    def limit_label(self) -> str:
        return f"{self.max_track_bytes // (1024 * 1024)} MiB"

    @property
    def max_base64_chars(self) -> int:
        """Return the largest Base64 payload allowed for the byte limit."""
        return 4 * ((self.max_track_bytes + 2) // 3)

    def decode_base64(self, payload: str) -> bytes:
        """Decode standard, URL-safe, wrapped, unpadded, or data-URL Base64."""
        text = payload.strip()
        if text[:5].casefold() == "data:":
            header, separator, text = text.partition(",")
            if not separator or not header.casefold().endswith(";base64"):
                raise ValueError("Track data URLs must contain Base64-encoded data.")
        text = re.sub(r"\s+", "", text)
        if len(text) > self.max_base64_chars:
            raise ValueError(f"Track content exceeds the {self.limit_label} limit.")
        text = text.replace("-", "+").replace("_", "/")
        text += "=" * (-len(text) % 4)
        try:
            return base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("content_base64 must be valid base64 data.") from error

    def detect_format(self, data: bytes) -> str:
        """Return the format (MP3, WAV, FLAC, OGG, M4A) of valid, bounded audio bytes."""
        if not data or len(data) > self.max_track_bytes:
            raise ValueError(f"Track content is empty or exceeds the {self.limit_label} limit.")
        try:
            probed = self.probe.probe(data)
        except AudioToolError as error:
            raise ValueError("Content is not a valid audio file.") from error
        detected = probed["format"]
        if detected not in self.FORMAT_EXTENSIONS:
            supported = ", ".join(self.FORMAT_EXTENSIONS)
            raise ValueError(f"{detected} audio is not supported; use {supported}.")
        return detected

    def validate(self, name: str, data: bytes) -> bytes:
        """Require ``data`` to be audio whose format matches ``name``."""
        detected = self.detect_format(data)
        expected = self.allowed_formats[Path(name).suffix.lower()]
        if detected != expected:
            raise ValueError(f"Track content is {detected}, filename expects {expected}.")
        return data

    def decode(self, name: str, content_base64: str) -> bytes:
        return self.validate(name, self.decode_base64(content_base64))

    def name_for(self, requested: str | None, detected: str) -> str:
        """Turn a requested name into a plain filename whose extension matches.

        Directories are dropped, and a missing or wrong extension is replaced
        with the detected format's (``song.wav`` holding MP3 -> ``song.mp3``).
        """
        name = Path((requested or "").strip().replace("\\", "/")).name
        stem, suffix = Path(name).stem, Path(name).suffix.lower()
        if suffix not in self.allowed_formats:
            stem = name
        stem = stem.strip().lstrip(".")
        if not stem:
            stem = self.DEFAULT_STEM
        if suffix in self.allowed_formats and self.allowed_formats[suffix] == detected:
            return f"{stem}{Path(name).suffix}"
        return f"{stem}{self.FORMAT_EXTENSIONS[detected]}"


UPLOAD_PREFIX = re.compile(r"[0-9a-f]{32}_(?=.)", re.IGNORECASE)


def display_name(stored_name: str) -> str:
    """Drop the internal upload prefix (32 hex characters and ``_``) from a filename."""
    return UPLOAD_PREFIX.sub("", stored_name, count=1)


class TrackArchive:
    """Write original track files into a ZIP on disk.

    Entries are stored uncompressed: lossy formats are already compressed, and
    deflating WAV or FLAC costs CPU for little gain.
    """

    @staticmethod
    def entry_name(stored_name: str) -> str:
        """Drop the internal upload prefix so entries keep their original names."""
        return display_name(stored_name)

    @classmethod
    def entry_names(cls, paths: list[Path]) -> list[str]:
        """Return unique entry names, numbering duplicates like ``song (2).mp3``."""
        names: list[str] = []
        taken: set[str] = set()
        for path in paths:
            name = cls.entry_name(path.name)
            stem, suffix = Path(name).stem, Path(name).suffix
            counter = 2
            while name.casefold() in taken:
                name = f"{stem} ({counter}){suffix}"
                counter += 1
            taken.add(name.casefold())
            names.append(name)
        return names

    @classmethod
    def write(cls, paths: list[Path], destination: Path) -> None:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as bundle:
            for path, name in zip(paths, cls.entry_names(paths)):
                bundle.write(path, arcname=name)
