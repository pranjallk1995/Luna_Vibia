"""Compose and run the Luna Vibia MCP and HTTP server."""

import uvicorn
from mcp.server.fastmcp import FastMCP

from app.transport.branding import ServerBranding
from app.core.config import AppConfig
from app.data.database import Database
from app.transport.http_routes import VibiaHTTPRoutes
from app.transport.mcp_tools import VibiaMCPTools
from app.core.models import MetadataRules
from app.integrations.remote import TrackSourceResolver
from app.data.repositories import TrackRepository, PublicURLRepository
from app.services.application import VibiaService
from app.integrations.captioning import OllamaCaptioner
from app.integrations.clap import ClapEncoder
from app.integrations.speakers import SpeakerPlayer, WindowsSpeakerHelper
from app.integrations.visia import VisiaImageCatalog


class LunaVibiaApplication:
    """Compose and own the concrete Luna Vibia dependencies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.database = Database(config.database_url)
        self.database.initialize_schema()
        self.service = VibiaService.create(
            config,
            TrackRepository(self.database),
            PublicURLRepository(self.database),
            OllamaCaptioner(
                config.ollama_url,
                config.caption_model,
                MetadataRules(config.max_tags, config.search_stop_words),
            ),
            ClapEncoder(),
            VisiaImageCatalog(config.visia_api_url, config.placeholder_cover_id),
            SpeakerPlayer(
                WindowsSpeakerHelper(config.speaker_helper_url, config.api_token)
                if config.speaker_helper_url
                else None
            ),
        )
        self.branding = ServerBranding(config.mcp_public_url)
        self.mcp = FastMCP(
            "Luna Vibia", host=config.host, port=config.port, icons=self.branding.mcp_icons()
        )
        VibiaMCPTools(
            self.mcp,
            self.service,
            TrackSourceResolver(
                self.service.visible.decoder, config.max_track_bytes, config.max_upload_redirects
            ),
        )
        VibiaHTTPRoutes(self.mcp, self.service, self.branding, config.api_token)

    def run(self) -> None:
        """Serve Luna Vibia over the streamable HTTP transport."""
        uvicorn.run(self.mcp.streamable_http_app(), host=self.config.host, port=self.config.port)


application = LunaVibiaApplication(AppConfig.from_env())
mcp = application.mcp

if __name__ == "__main__":
    application.run()
