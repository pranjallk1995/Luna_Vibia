"""A PIN in front of hidden items; this module is identical in Luna Visia, Lexia, and Vibia.

Each person sets one PIN at Luna Sentia, which checks it and locks it after wrong guesses.
Typing it into this app's Hidden tab unlocks the hidden items for this sign-in session,
until it has been idle for ``IDLE_SECONDS`` or open for ``MOST_SECONDS``. Until then the
gateway refuses the hidden collection, changes to it, and the files of hidden items, so a
copied file link does not open a hidden item either.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

from config import SSOConfig

LOCKED = "Enter your PIN to see hidden items."


class HiddenPin:
    """Which sessions have unlocked hidden items, and which item names are hidden."""

    IDLE_SECONDS = 10 * 60
    MOST_SECONDS = 60 * 60
    # How long a person's list of hidden names is trusted before asking the backend again.
    NAMES_SECONDS = 30

    def __init__(self, config: SSOConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.public_url = config.public_url.rstrip("/")
        self.internal_url = config.internal_url.rstrip("/")
        self.client = httpx.AsyncClient(transport=transport, timeout=SSOConfig.LOOKUP_TIMEOUT_SECONDS)
        # Session-token hash -> (idle deadline, hard deadline), on the monotonic clock.
        self.unlocks: dict[str, tuple[float, float]] = {}
        # Person -> (when fetched, their hidden names).
        self.names: dict[str, tuple[float, frozenset[str]]] = {}

    @staticmethod
    def key(token: str | None) -> str:
        return hashlib.sha256((token or "").encode()).hexdigest()

    # Unlocking

    def is_unlocked(self, token: str | None) -> bool:
        """Whether this session has unlocked hidden items; using them keeps them unlocked."""
        if not token:
            return False
        now = time.monotonic()
        key = self.key(token)
        idle, most = self.unlocks.get(key, (0.0, 0.0))
        if now >= idle or now >= most:
            self.unlocks.pop(key, None)
            return False
        self.unlocks[key] = (min(now + self.IDLE_SECONDS, most), most)
        return True

    def lock(self, token: str | None) -> None:
        self.unlocks.pop(self.key(token), None)

    def settings_url(self, here: str) -> str:
        return f"{self.public_url}/pin?next={quote(here, safe='')}"

    async def status(self, token: str, here: str) -> dict[str, Any]:
        """What the Hidden tab should show: a PIN to set, a PIN to type, or the items."""
        unlocked = self.is_unlocked(token)
        answer: dict[str, Any] = {"unlocked": unlocked, "settings_url": self.settings_url(here)}
        if unlocked:
            return {**answer, "pin_set": True, "locked_seconds": 0}
        response = await self.client.get(
            f"{self.internal_url}/pin/status", headers={SSOConfig.SESSION_HEADER: token}
        )
        response.raise_for_status()
        state = response.json()
        return {**answer, "pin_set": bool(state.get("pin_set")), "locked_seconds": int(state.get("locked_seconds") or 0)}

    async def unlock(self, token: str, pin: str) -> tuple[int, dict[str, Any]]:
        """Ask Sentia whether ``pin`` is right; unlock this session if it is."""
        response = await self.client.post(
            f"{self.internal_url}/pin/verify", json={"pin": pin}, headers={SSOConfig.SESSION_HEADER: token}
        )
        if response.status_code >= 500:
            response.raise_for_status()
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code == 200 and body.get("ok") is True:
            now = time.monotonic()
            self.unlocks[self.key(token)] = (now + self.IDLE_SECONDS, now + self.MOST_SECONDS)
            self.forget_expired(now)
            return 200, {"unlocked": True}
        return response.status_code, {key: value for key, value in body.items() if key != "ok"}

    def forget_expired(self, now: float) -> None:
        self.unlocks = {key: deadlines for key, deadlines in self.unlocks.items() if min(deadlines) > now}

    # Hidden names, so a hidden item's files stay locked too

    async def hidden_names(self, user_id: str, fetch: Callable[[], Awaitable[set[str]]]) -> frozenset[str]:
        """This person's hidden item names, asked for again after ``NAMES_SECONDS``."""
        cached = self.names.get(user_id)
        if cached and time.monotonic() - cached[0] < self.NAMES_SECONDS:
            return cached[1]
        names = frozenset(await fetch())
        self.names[user_id] = (time.monotonic(), names)
        return names

    def remember_names(self, user_id: str, names: set[str]) -> None:
        self.names[user_id] = (time.monotonic(), frozenset(names))

    def forget_names(self, user_id: str) -> None:
        """Something was hidden, shown, renamed, or deleted: ask for the names again next time."""
        self.names.pop(user_id, None)
