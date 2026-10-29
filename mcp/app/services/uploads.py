"""Single-use upload links for clients that can send file bytes over HTTP."""

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone


class UploadLinkNotFound(LookupError):
    """Raised for an upload token that expired, was used, or never existed."""


@dataclass(frozen=True)
class UploadTicket:
    """Permission to upload one track under a requested name."""

    token: str
    name: str
    replace: bool
    expires_at: float

    @property
    def expires_at_iso(self) -> str:
        return datetime.fromtimestamp(self.expires_at, timezone.utc).isoformat(timespec="seconds")


class UploadLinkStore:
    """In-memory upload tickets that are consumed by their first successful use."""

    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._tickets: dict[str, UploadTicket] = {}
        self._lock = threading.Lock()

    def create(self, name: str, replace: bool) -> UploadTicket:
        ticket = UploadTicket(
            token=secrets.token_urlsafe(32),
            name=name,
            replace=replace,
            expires_at=time.time() + self.ttl_seconds,
        )
        with self._lock:
            self._purge_expired()
            self._tickets[ticket.token] = ticket
        return ticket

    def claim(self, token: str) -> UploadTicket:
        """Take a live ticket so no concurrent request can use it."""
        with self._lock:
            self._purge_expired()
            ticket = self._tickets.pop(token, None)
        if ticket is None:
            raise UploadLinkNotFound(
                "This upload link has expired, was already used, or does not exist."
            )
        return ticket

    def release(self, ticket: UploadTicket) -> None:
        """Return a claimed ticket after a failed upload so the client can retry."""
        if ticket.expires_at > time.time():
            with self._lock:
                self._tickets[ticket.token] = ticket

    def _purge_expired(self) -> None:
        now = time.time()
        for token in [token for token, ticket in self._tickets.items() if ticket.expires_at <= now]:
            del self._tickets[token]
