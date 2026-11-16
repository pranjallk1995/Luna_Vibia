"""Compose and run the Luna Vibia MCP and HTTP server."""

import logging

import uvicorn

from app.transport.branding import ServerBranding
from app.core import tenancy
from app.core.config import AppConfig
from app.data.database import Database
from app.data.tenants import adopt_loose_files, remove_folder
from app.transport.http_routes import VibiaHTTPRoutes
from app.transport.mcp_tools import SERVER_INSTRUCTIONS, VibiaMCP, VibiaMCPTools
from app.core.models import MetadataRules
from app.integrations.remote import TrackSourceResolver
from app.data.repositories import TrackRepository, PublicURLRepository
from app.services.application import VibiaService
from app.services.starter import StarterLibrary
from app.integrations.captioning import OllamaCaptioner
from app.integrations.clap import IdleClapEncoder
from app.integrations.speakers import OwnerSpeakers, SpeakerPlayer, WindowsSpeakerHelper
from app.integrations.visia import VisiaImageCatalog

# httpx logs every request's full URL at INFO, and music and file links are signed.
logging.getLogger("httpx").setLevel(logging.WARNING)


class LunaVibiaApplication:
    """Compose and own the concrete Luna Vibia dependencies."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.database = Database(config.database_url)
        self.database.initialize_schema()
        adopt_loose_files(config.track_dir)
        with tenancy.acting_as(tenancy.OWNER):
            self.service = VibiaService.create(
                config,
                TrackRepository(self.database),
                PublicURLRepository(self.database),
                OllamaCaptioner(
                    config.ollama_url,
                    config.caption_model,
                    MetadataRules(config.max_tags, config.search_stop_words),
                ),
                IdleClapEncoder(device=config.clap_device),
                VisiaImageCatalog(
                    config.visia_api_url,
                    config.placeholder_cover_id,
                    companion_token=config.visia_companion_token,
                ),
                OwnerSpeakers(
                    SpeakerPlayer(
                        WindowsSpeakerHelper(config.speaker_helper_url, config.api_token)
                        if config.speaker_helper_url
                        else None
                    )
                ),
            )
        self.service.starter = StarterLibrary(self.database, config.track_dir)
        self.database.tenants.after_create = self.prepare_person
        # Anyone who joined earlier gets tracks chosen since.
        self.service.starter.deliver_to_everyone()
        self.branding = ServerBranding(config.mcp_public_url)
        self.mcp = VibiaMCP(
            "Luna Vibia",
            app="vibia",
            remove_user=self.remove_user,
            public_url=config.mcp_public_url,
            api_token=config.api_token,
            open_paths=("/api/public/", "/api/downloads/", "/api/uploads/"),
            instructions=SERVER_INSTRUCTIONS,
            host=config.host,
            port=config.port,
            icons=self.branding.mcp_icons(),
        )
        VibiaMCPTools(
            self.mcp,
            self.service,
            TrackSourceResolver(
                self.service.visible.decoder, config.max_track_bytes, config.max_upload_redirects
            ),
        )
        VibiaHTTPRoutes(self.mcp, self.service, self.branding, config.api_token)

    def prepare_person(self) -> None:
        """Give someone what they start with, the first time this process needs them."""
        # Public links are served by this backend, so a new person's start at its address.
        self.service.urls.seed(self.config.mcp_public_url or self.config.public_base_url)
        self.service.starter.deliver(tenancy.current())

    def remove_user(self, user_id: str) -> None:
        """Delete everything this person has in this app."""
        self.database.tenants.remove(user_id)
        remove_folder(self.config.track_dir, user_id)
        self.service.downloads.store.remove_user(user_id)


    def run(self) -> None:
        """Serve Luna Vibia over the streamable HTTP transport."""
        uvicorn.run(self.mcp.streamable_http_app(), host=self.config.host, port=self.config.port)


application = LunaVibiaApplication(AppConfig.from_env())
mcp = application.mcp

if __name__ == "__main__":
    application.run()
