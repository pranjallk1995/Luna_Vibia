"""Single sign-on through Luna Sentia's auth service, for a Luna app's UI gateway.

One Google sign-in at Sentia sets the ``luna_sso`` cookie for the parent domain
of every app. This module asks Sentia over the private network whose session
that cookie belongs to, and applies this app's own email allowlist. Signing out
at Sentia signs out of every Luna app.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any
from urllib.parse import quote

import httpx

from config import SSOConfig


class LunaSingleSignOn:
    """Resolve a session cookie to a person, and build Sentia's sign-in and sign-out links."""

    def __init__(
        self,
        allowed_emails: frozenset[str],
        config: SSOConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.allowed_emails = allowed_emails
        self.public_url = config.public_url.rstrip("/")
        self.internal_url = config.internal_url.rstrip("/")
        self.client = httpx.AsyncClient(transport=transport, timeout=SSOConfig.LOOKUP_TIMEOUT_SECONDS)
        self.sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()

    # Identity

    def is_allowed(self, user: dict[str, Any] | None) -> bool:
        email = str((user or {}).get("email", "")).strip().casefold()
        return bool(email and email in self.allowed_emails and (user or {}).get("email_verified") is True)

    async def lookup(self, token: str) -> dict[str, Any] | None:
        """Ask Sentia who the session belongs to; None when it is unknown or expired."""
        response = await self.client.get(
            f"{self.internal_url}/session", headers={SSOConfig.SESSION_HEADER: token}
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        return response.json()

    async def user(self, token: str | None) -> dict[str, Any] | None:
        """The session's person, trusted for ``RECHECK_SECONDS`` before asking Sentia again."""
        if not token:
            return None
        cached = self.sessions.get(token)
        if cached and time.monotonic() - cached["checked"] < SSOConfig.RECHECK_SECONDS:
            return cached["user"]
        try:
            user = await self.lookup(token)
        except httpx.HTTPError:
            # Sentia briefly unreachable: keep a session confirmed earlier, never invent one.
            return cached["user"] if cached else None
        self.sessions[token] = {"user": user, "checked": time.monotonic()}
        self.sessions.move_to_end(token)
        while len(self.sessions) > SSOConfig.SESSION_CACHE_ENTRIES:
            self.sessions.popitem(last=False)
        return user

    # Addresses

    def login_url(self, here: str) -> str:
        return f"{self.public_url}/login?next={quote(here, safe='')}"

    def logout_url(self, here: str) -> str:
        return f"{self.public_url}/logout?next={quote(here, safe='')}"
