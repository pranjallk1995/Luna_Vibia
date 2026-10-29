"""REST routes used by the Luna Vibia Streamlit interface and public track links."""

from collections.abc import Awaitable, Callable
from typing import Any

import anyio
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.transport.branding import ServerBranding
from app.transport.auth import APIAuthenticator
from app.core.models import MetadataChange
from app.services.application import VibiaService
from app.services.uploads import UploadLinkNotFound

Handler = Callable[[Request], Awaitable[Any]]

# Served types for the stored formats, so browsers and players stream them inline.
AUDIO_TYPES = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}


class VibiaHTTPRoutes:
    """Translate HTTP requests into service calls and results into JSON."""

    PUBLIC_TRACK_HEADERS = {
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    }
    ICON_HEADERS = {
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    }

    def __init__(
        self,
        server: FastMCP,
        service: VibiaService,
        branding: ServerBranding,
        api_token: str,
    ) -> None:
        self.server = server
        self.service = service
        self.branding = branding
        self.authenticator = APIAuthenticator(api_token)
        self._register()

    @staticmethod
    def error(error: Exception) -> JSONResponse:
        status = 401 if isinstance(error, PermissionError) else 400
        return JSONResponse({"error": str(error)}, status_code=status)

    @staticmethod
    async def payload(request: Request) -> dict[str, Any]:
        """Parse a JSON object request body."""
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    @classmethod
    async def metadata_change(cls, request: Request) -> MetadataChange:
        payload = await cls.payload(request)
        return MetadataChange(
            caption=payload.get("caption"),
            add_tags=payload.get("add_tags"),
            remove_tags=payload.get("remove_tags"),
        )

    @staticmethod
    def name(request: Request) -> str:
        return request.path_params["name"]

    def route(
        self,
        method: str,
        path: str,
        handler: Handler,
        status: int = 200,
        *,
        protected: bool = False,
    ) -> None:
        """Register ``handler`` with uniform error translation."""

        async def endpoint(request: Request) -> Response:
            try:
                if protected:
                    rejection = self.authenticator.rejection(request)
                    if rejection is not None:
                        return rejection
                result = await handler(request)
                if isinstance(result, Response):
                    return result
                return JSONResponse(result, status_code=status)
            except Exception as error:
                return self.error(error)

        self.server.custom_route(path, methods=[method])(endpoint)

    def _register(self) -> None:
        self.route("GET", "/health", self.health)
        self._register_icons()
        self._register_tracks()
        self._register_favorites()
        self._register_playback()
        self._register_downloads()
        self._register_uploads()
        self._register_hidden_tracks()

    async def health(self, request: Request) -> dict:
        return {"status": "ok", "service": "luna-vibia"}

    def _register_icons(self) -> None:
        branding = self.branding

        async def favicon(request: Request):
            return FileResponse(
                branding.favicon_path(), media_type="image/x-icon", headers=self.ICON_HEADERS
            )

        async def icon(request: Request):
            return FileResponse(
                branding.icon_path(self.name(request)),
                media_type="image/png",
                headers=self.ICON_HEADERS,
            )

        async def home(request: Request):
            return HTMLResponse(branding.home_page(), headers=self.ICON_HEADERS)

        self.route("GET", "/", home)
        self.route("GET", "/favicon.ico", favicon)
        self.route("GET", "/icons/{name}", icon)

    def _register_tracks(self) -> None:
        visible = self.service.visible

        async def metadata(request: Request):
            return {"tracks": visible.list()}

        async def public_track(request: Request):
            path = visible.public_path(self.name(request))
            return FileResponse(
                path,
                media_type=AUDIO_TYPES.get(path.suffix.lower(), "application/octet-stream"),
                headers={
                    "Content-Disposition": f'inline; filename="{path.name}"',
                    **self.PUBLIC_TRACK_HEADERS,
                },
            )

        async def upload(request: Request):
            payload = await self.payload(request)
            given = {key: payload.get(key) for key in ("title", "artist", "notes")}
            created = await anyio.to_thread.run_sync(
                visible.ingest, payload["name"], payload["content_base64"], False, given
            )
            return {"status": "created", **created}

        async def set_cover(request: Request):
            payload = await self.payload(request)
            return {
                "status": "cover_updated",
                **await anyio.to_thread.run_sync(visible.set_cover, self.name(request), payload.get("cover_url")),
            }

        async def delete(request: Request):
            return visible.remove(self.name(request))

        async def rename(request: Request):
            payload = await self.payload(request)
            return visible.rename(self.name(request), payload.get("new_name", ""))

        async def update_metadata(request: Request):
            change = await self.metadata_change(request)
            return {
                "status": "metadata_updated",
                **visible.update_metadata(self.name(request), change),
            }

        self.route("GET", "/api/metadata", metadata)
        self.route("GET", "/api/public/tracks/{name}", public_track)
        self.route("POST", "/api/tracks", upload, 201)
        self.route("DELETE", "/api/tracks/{name}", delete)
        self.route("POST", "/api/tracks/{name}/rename", rename)
        self.route("POST", "/api/tracks/{name}/metadata", update_metadata)
        self.route("POST", "/api/tracks/{name}/cover", set_cover)

    def _register_downloads(self) -> None:
        downloads = self.service.downloads

        async def download(request: Request):
            try:
                ticket, path = downloads.archive(request.path_params["token"])
            except FileNotFoundError as error:
                return JSONResponse({"error": str(error)}, status_code=404)
            return FileResponse(
                path,
                media_type="application/zip",
                filename=ticket.file_name,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )

        self.route("GET", "/api/downloads/{token}", download)

    @staticmethod
    async def read_upload(request: Request, max_bytes: int) -> tuple[bytes, str | None]:
        """Read a raw or multipart (field ``file``) upload body, enforcing ``max_bytes``."""
        too_large = ValueError(f"Upload exceeds the {max_bytes // (1024 * 1024)} MiB limit.")
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            async with request.form(max_files=1) as form:
                upload = form.get("file")
                if upload is None or isinstance(upload, str):
                    raise ValueError("Send the track in a multipart field named 'file'.")
                data = await upload.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise too_large
                return data, upload.filename
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > max_bytes:
                raise too_large
        return bytes(data), None

    def _register_uploads(self) -> None:
        uploads = self.service.uploads

        async def receive(request: Request):
            data, file_name = await self.read_upload(request, uploads.max_bytes)
            try:
                return await anyio.to_thread.run_sync(
                    uploads.receive, request.path_params["token"], data, file_name
                )
            except UploadLinkNotFound as error:
                return JSONResponse({"error": str(error)}, status_code=404)

        self.route("POST", "/api/uploads/{token}", receive, 201)

    def _register_favorites(self) -> None:
        visible = self.service.visible

        async def favorites(request: Request):
            return {"tracks": visible.favorites()}

        async def update_favorites(request: Request):
            payload = await self.payload(request)
            favorite = payload.get("favorite")
            if not isinstance(favorite, bool):
                raise ValueError("favorite must be true or false.")
            return visible.set_favorite(payload.get("names", []), favorite)

        self.route("GET", "/api/favorites", favorites)
        self.route("POST", "/api/favorites", update_favorites)

    def _register_playback(self) -> None:
        playback_service = self.service.playback

        async def playback(request: Request):
            return await anyio.to_thread.run_sync(playback_service.player.live_status)

        self.route("GET", "/api/playback", playback)

    def _register_hidden_tracks(self) -> None:
        hidden = self.service.hidden

        async def tracks(request: Request):
            return {"tracks": hidden.list()}

        async def update_metadata(request: Request):
            change = await self.metadata_change(request)
            return {
                "status": "metadata_updated",
                **hidden.update_metadata(self.name(request), change),
            }

        async def hide(request: Request):
            return hidden.set_hidden((await self.payload(request)).get("names", []), True)

        async def restore(request: Request):
            return hidden.set_hidden((await self.payload(request)).get("names", []), False)

        async def delete(request: Request):
            return hidden.remove_many((await self.payload(request)).get("names", []))

        self.route("GET", "/api/hidden/tracks", tracks, protected=True)
        self.route(
            "POST", "/api/hidden/tracks/{name}/metadata", update_metadata, protected=True
        )
        self.route("POST", "/api/hidden/hide", hide, protected=True)
        self.route("POST", "/api/hidden/delete", delete, protected=True)
        self.route("POST", "/api/hidden/restore", restore, protected=True)
