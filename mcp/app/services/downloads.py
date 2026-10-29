"""ZIP archives served through unguessable, restart-safe download links."""

import json
import re
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services.media import TrackArchive
from app.core.config import AppConfig


@dataclass(frozen=True)
class DownloadTicket:
    """One prepared archive and the capability token that unlocks it."""

    token: str
    file_name: str
    track_count: int
    size_bytes: int
    expires_at: float

    @property
    def expires_at_iso(self) -> str:
        return datetime.fromtimestamp(self.expires_at, timezone.utc).isoformat(timespec="seconds")


class DownloadStore:
    """Keep archives and their tickets on disk so links survive restarts.

    Each archive ``<token>.zip`` has a ``<token>.json`` sidecar holding its
    ticket. The sidecar is written last and atomically, so a link only exists
    once its archive is complete. Expired archives are purged, and the oldest
    are evicted when the store exceeds ``max_total_bytes``.
    """

    FILE_NAME = "luna-vibia-tracks.zip"
    TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
    NOT_FOUND_MESSAGE = "This download link has expired or does not exist."

    def __init__(self, directory: Path, ttl_seconds: int, max_total_bytes: int) -> None:
        self.directory = directory
        self.ttl_seconds = ttl_seconds
        self.max_total_bytes = max_total_bytes
        self.directory.mkdir(parents=True, exist_ok=True)
        self.purge()

    def archive_path(self, token: str) -> Path:
        return self.directory / f"{token}.zip"

    def _ticket_path(self, token: str) -> Path:
        return self.directory / f"{token}.json"

    def create(self, paths: list[Path]) -> DownloadTicket:
        """Archive ``paths`` and return a ticket valid for the TTL."""
        self.purge()
        token = secrets.token_urlsafe(32)
        archive = self.archive_path(token)
        partial = archive.with_suffix(".zip.part")
        try:
            TrackArchive.write(paths, partial)
            partial.replace(archive)
            ticket = DownloadTicket(
                token=token,
                file_name=self.FILE_NAME,
                track_count=len(paths),
                size_bytes=archive.stat().st_size,
                expires_at=time.time() + self.ttl_seconds,
            )
            sidecar = self._ticket_path(token).with_suffix(".json.part")
            sidecar.write_text(json.dumps(asdict(ticket)))
            sidecar.replace(self._ticket_path(token))
        except BaseException:
            for path in (partial, archive, self._ticket_path(token).with_suffix(".json.part")):
                path.unlink(missing_ok=True)
            raise
        self.purge(keep=token)
        return ticket

    def resolve(self, token: str) -> DownloadTicket:
        """Return a live ticket or raise ``FileNotFoundError``."""
        ticket = self._load(token) if self.TOKEN_PATTERN.fullmatch(token) else None
        if ticket is None or ticket.expires_at <= time.time() or not self.archive_path(token).is_file():
            raise FileNotFoundError(self.NOT_FOUND_MESSAGE)
        return ticket

    def _load(self, token: str) -> DownloadTicket | None:
        try:
            return DownloadTicket(**json.loads(self._ticket_path(token).read_text()))
        except (OSError, ValueError, TypeError):
            return None

    def _remove(self, token: str) -> None:
        self._ticket_path(token).unlink(missing_ok=True)
        self.archive_path(token).unlink(missing_ok=True)

    def purge(self, keep: str | None = None) -> None:
        """Drop expired or incomplete archives, then evict the oldest over the cap."""
        now = time.time()
        live: list[DownloadTicket] = []
        for sidecar in self.directory.glob("*.json"):
            ticket = self._load(sidecar.stem)
            if ticket is None or ticket.expires_at <= now or not self.archive_path(sidecar.stem).is_file():
                self._remove(sidecar.stem)
            else:
                live.append(ticket)
        tokens = {ticket.token for ticket in live}
        cutoff = now - AppConfig.DOWNLOAD_LEFTOVER_GRACE_SECONDS
        leftovers = [path for path in self.directory.glob("*.zip") if path.stem not in tokens]
        for path in [*leftovers, *self.directory.glob("*.part")]:
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                continue
        total = sum(ticket.size_bytes for ticket in live)
        for ticket in sorted(live, key=lambda ticket: ticket.expires_at):
            if total <= self.max_total_bytes:
                break
            if ticket.token != keep:
                self._remove(ticket.token)
                total -= ticket.size_bytes
