"""Authentication boundary for OAuth-gated UI backend requests."""

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class APIAuthenticator:
    """Validate the private credential shared with the OAuth-gated UI."""

    def __init__(self, token: str) -> None:
        if len(token) < 32:
            raise ValueError("API token must contain at least 32 characters.")
        self._token = token

    def rejection(self, request: Request) -> Response | None:
        scheme, separator, credential = request.headers.get("authorization", "").partition(" ")
        if (
            separator
            and scheme.lower() == "bearer"
            and credential
            and hmac.compare_digest(credential, self._token)
        ):
            return None
        return JSONResponse(
            {"error": "Authentication required"},
            status_code=401,
            headers={
                "WWW-Authenticate": "Bearer",
                "Cache-Control": "no-store",
            },
        )
