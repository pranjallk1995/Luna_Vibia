"""Password, reset-PIN, and session handling for hidden tracks."""

import hashlib
import hmac
import re
import secrets
import threading
import time

from app.data.repositories import CredentialRepository, StoredCredentials
from app.core.config import AppConfig


class CredentialPolicy:
    """Validate and hash Hidden Vault secrets."""

    def __init__(self, iterations: int) -> None:
        self.iterations = iterations

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 8:
            raise ValueError("Password must contain at least 8 characters.")

    @staticmethod
    def validate_pin(pin: str) -> None:
        if not re.fullmatch(r"\d{8}", pin):
            raise ValueError("Reset PIN must be exactly 8 digits.")

    @staticmethod
    def hash(value: str, salt: bytes, iterations: int) -> bytes:
        """Derive a PBKDF2-SHA256 hash for ``value``."""
        return hashlib.pbkdf2_hmac("sha256", value.encode(), salt, iterations)

    def new_hash(self, value: str) -> tuple[bytes, bytes]:
        """Return a fresh salt and the hash of ``value`` with it."""
        salt = secrets.token_bytes(AppConfig.CREDENTIAL_SALT_BYTES)
        return salt, self.hash(value, salt, self.iterations)

    def matches(self, value: str, salt: bytes, expected: bytes, iterations: int) -> bool:
        """Compare in constant time using the iteration count stored with the hash."""
        return hmac.compare_digest(self.hash(value, salt, iterations), expected)


class SessionStore:
    """Process-local sliding-expiry session tokens.

    Tokens stay in memory so database access cannot reveal them.
    """

    def __init__(self, session_seconds: int) -> None:
        self.session_seconds = session_seconds
        self._sessions: dict[str, float] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._sessions = {
                key: expiry for key, expiry in self._sessions.items() if expiry > now
            }
            self._sessions[token] = now + self.session_seconds
        return token

    def require(self, token: str | None) -> None:
        """Require a live token and extend its sliding expiration window."""
        now = time.monotonic()
        with self._lock:
            expiry = self._sessions.get(token or "", 0)
            if expiry <= now:
                self._sessions.pop(token or "", None)
                raise PermissionError("Hidden-vault session is missing or expired.")
            self._sessions[token] = now + self.session_seconds

    def revoke(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    def revoke_all(self) -> None:
        with self._lock:
            self._sessions.clear()


class HiddenVaultAuth:
    """Persist hashed credentials and issue short-lived in-memory sessions."""

    def __init__(
        self,
        credentials: CredentialRepository,
        policy: CredentialPolicy,
        sessions: SessionStore,
    ) -> None:
        self.credentials = credentials
        self.policy = policy
        self.sessions = sessions

    def configured(self) -> bool:
        """Return whether Hidden Vault credentials have been configured."""
        return self.credentials.get() is not None

    def _stored(self) -> StoredCredentials:
        stored = self.credentials.get()
        if stored is None:
            raise ValueError("Create a hidden-vault password first.")
        return stored

    def setup(self, password: str, pin: str) -> str:
        """Create hidden-vault credentials and return a new session token."""
        self.policy.validate_password(password)
        self.policy.validate_pin(pin)
        password_salt, password_hash = self.policy.new_hash(password)
        pin_salt, pin_hash = self.policy.new_hash(pin)
        created = self.credentials.create(
            StoredCredentials(
                password_salt, password_hash, pin_salt, pin_hash, self.policy.iterations
            )
        )
        if not created:
            raise ValueError("A hidden-vault password has already been created.")
        return self.sessions.create()

    def login(self, password: str) -> str:
        """Verify the password and create a session token."""
        stored = self._stored()
        if not self.policy.matches(
            password, stored.password_salt, stored.password_hash, stored.iterations
        ):
            raise PermissionError("Incorrect password.")
        return self.sessions.create()

    def reset(self, pin: str, new_password: str) -> str:
        """Replace the password after validating the eight-digit reset PIN."""
        self.policy.validate_pin(pin)
        self.policy.validate_password(new_password)
        stored = self._stored()
        if not self.policy.matches(pin, stored.pin_salt, stored.pin_hash, stored.iterations):
            raise PermissionError("Incorrect reset PIN.")
        salt, password_hash = self.policy.new_hash(new_password)
        self.credentials.update_password(salt, password_hash, self.policy.iterations)
        self.sessions.revoke_all()
        return self.sessions.create()

    def require(self, token: str | None) -> None:
        self.sessions.require(token)

    def logout(self, token: str | None) -> None:
        self.sessions.revoke(token)
