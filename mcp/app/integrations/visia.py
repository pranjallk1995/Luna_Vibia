"""Verify cover-art URLs against the Luna Visia image catalog."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from app.core.config import AppConfig


class VisiaUnavailableError(RuntimeError):
    """Raised when Luna Visia cannot be reached to verify a cover image."""


class VisiaImageCatalog:
    """Resolve a cover URL to the canonical public URL of a visible Visia image.

    Only immutable image-ID URLs (``.../api/public/images/<uuid>``) are accepted,
    because filenames can change in Visia while image IDs never do. The ID must
    belong to a visible image, and the URL Visia publishes for it is returned.
    """

    PUBLIC_PATH = re.compile(
        r"/api/public/images/"
        r"(?P<image_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
        re.IGNORECASE,
    )
    SEARCH_HINT = (
        "Search Luna Visia for an image that suits the track and pass the public_url it "
        "returns; if none fits, omit cover_url to use the Luna Vibia audio placeholder."
    )

    def __init__(
        self,
        api_url: str,
        placeholder_image_id: str = "",
        timeout: float = AppConfig.VISIA_TIMEOUT_SECONDS,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.placeholder_image_id = placeholder_image_id.lower()
        self.timeout = timeout

    @classmethod
    def image_id(cls, cover_url: str) -> str:
        """Extract the image ID, rejecting data URIs and filename-based URLs."""
        parsed = urlparse(cover_url.strip())
        match = cls.PUBLIC_PATH.search(parsed.path)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not match:
            raise ValueError(
                "cover_url must be a Luna Visia image-ID URL ending in "
                f"/api/public/images/<image-id>. {cls.SEARCH_HINT}"
            )
        return match["image_id"].lower()

    def images(self) -> list[dict]:
        try:
            response = httpx.get(f"{self.api_url}/api/metadata", timeout=self.timeout)
            response.raise_for_status()
            return response.json()["images"]
        except (httpx.HTTPError, ValueError, KeyError) as error:
            raise VisiaUnavailableError(
                f"Luna Visia is unavailable, so the cover image cannot be verified: {error}"
            ) from error

    def resolve(self, cover_url: str) -> str:
        """Return Visia's canonical public URL for the image ``cover_url`` names."""
        return self.resolve_id(self.image_id(cover_url))

    def placeholder_url(self) -> str | None:
        """The public URL of the audio placeholder in Visia, or None while none is configured."""
        if not self.placeholder_image_id:
            return None
        try:
            return self.resolve_id(self.placeholder_image_id)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"The Luna Vibia audio placeholder ({self.placeholder_image_id}) is missing from "
                "Luna Visia; restore it or set LUNAVIBIA_PLACEHOLDER_COVER_ID."
            ) from error

    def resolve_id(self, image_id: str) -> str:
        for image in self.images():
            if str(image.get("image_id", "")).lower() == image_id and not image.get("hidden"):
                return image["public_url"]
        raise FileNotFoundError(f"No visible Luna Visia image has ID {image_id}. {self.SEARCH_HINT}")
