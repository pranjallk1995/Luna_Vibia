"""The Luna Vibia icon set for MCP server info and HTTP favicons."""

import base64
import html
from pathlib import Path

from mcp.types import Icon

from app.core.config import AppConfig


class ServerBranding:
    """Expose the bundled icons as MCP ``Icon`` entries and servable files.

    Server-info icons are listed as public HTTPS URLs first (claude.ai only
    shows icons it can load by URL), then as embedded ``data:`` URIs for clients
    that cannot reach the server's public origin. The home page links the same
    icons so favicon crawlers find them too.
    """

    FAVICON = "favicon.ico"
    ICON_SIZES = (48, 96, 192, 512)
    SERVER_INFO_ICON_SIZES = (48, 96)

    def __init__(self, public_url: str = "", asset_dir: Path = AppConfig.ASSET_DIR, name: str = "Luna Vibia") -> None:
        self.public_url = public_url.rstrip("/")
        self.asset_dir = asset_dir
        self.name = name

    @staticmethod
    def icon_name(size: int) -> str:
        return f"icon-{size}.png"

    def favicon_path(self) -> Path:
        return self.asset_dir / self.FAVICON

    def icon_path(self, name: str) -> Path:
        """Resolve one bundled PNG by name, rejecting anything else."""
        if name not in {self.icon_name(size) for size in self.ICON_SIZES}:
            raise FileNotFoundError(f"Icon {name!r} was not found.")
        return self.asset_dir / name

    def mcp_icons(self) -> list[Icon]:
        """Return the icons advertised in the MCP ``initialize`` server info."""
        icons = [
            Icon(src=f"{self.public_url}/icons/{self.icon_name(size)}", mimeType="image/png", sizes=[f"{size}x{size}"])
            for size in self.ICON_SIZES
            if self.public_url
        ]
        for size in self.SERVER_INFO_ICON_SIZES:
            data = base64.b64encode(self.icon_path(self.icon_name(size)).read_bytes())
            icons.append(
                Icon(
                    src=f"data:image/png;base64,{data.decode('ascii')}",
                    mimeType="image/png",
                    sizes=[f"{size}x{size}"],
                )
            )
        return icons

    def home_page(self) -> str:
        """A minimal page at ``/`` whose icon links let favicon crawlers find the icon."""
        links = "".join(
            f'<link rel="icon" type="image/png" sizes="{size}x{size}" href="/icons/{self.icon_name(size)}">'
            for size in self.ICON_SIZES
        )
        name = html.escape(self.name)
        return (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{name}</title>'
            f'<link rel="icon" href="/{self.FAVICON}" sizes="any">{links}'
            f'<link rel="apple-touch-icon" href="/icons/{self.icon_name(192)}"></head>'
            f'<body><img src="/icons/{self.icon_name(96)}" width="48" height="48" alt="">'
            f"<h1>{name}</h1><p>MCP server. Connect at <code>/mcp</code>.</p></body></html>"
        )
