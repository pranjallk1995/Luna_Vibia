"""Single sign-on through Luna Sentia's auth service, shared by every Luna app UI.

One Google sign-in at Sentia sets the ``luna_sso`` cookie for the parent domain
of every app. This module reads that cookie, asks Sentia over the private
network whose session it is, and applies this app's own email allowlist.
Signing out here signs out of every Luna app.

The same file is copied into each app's ``ui/`` folder; keep the copies identical,
along with the ``SSOConfig`` settings block in each app's ``config.py``.
"""

from __future__ import annotations

import base64
import html
import time
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
import streamlit as st

from config import SSOConfig

SIGN_OUT_KEY = "luna_sso_sign_out"
CACHE_KEY = "luna_sso_user"

GOOGLE_LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
<path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.92h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.41z"/>
<path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.62-2.43l-3.24-2.54c-.9.6-2.05.96-3.38.96-2.6 0-4.81-1.76-5.6-4.13H3.06v2.62A10 10 0 0 0 12 22z"/>
<path fill="#FBBC05" d="M6.4 13.86A6 6 0 0 1 6.08 12c0-.65.11-1.28.32-1.86V7.52H3.06A10 10 0 0 0 2 12c0 1.61.39 3.14 1.06 4.48l3.34-2.62z"/>
<path fill="#EA4335" d="M12 6.01c1.47 0 2.79.5 3.83 1.5l2.87-2.87A9.63 9.63 0 0 0 12 2a10 10 0 0 0-8.94 5.52l3.34 2.62C7.19 7.77 9.4 6.01 12 6.01z"/>
</svg>"""


class LunaSingleSignOn:
    """Gate a Luna app behind Sentia's shared sign-in and this app's allowlist."""

    def __init__(self, allowed_emails: frozenset[str], config: SSOConfig) -> None:
        self.allowed_emails = allowed_emails
        self.public_url = config.public_url.rstrip("/")
        self.internal_url = config.internal_url.rstrip("/")

    # Identity

    def is_allowed(self, user: dict[str, Any] | None) -> bool:
        email = str((user or {}).get("email", "")).strip().casefold()
        return bool(email and email in self.allowed_emails and (user or {}).get("email_verified") is True)

    def lookup(self, token: str) -> dict[str, Any] | None:
        """Ask Sentia who the session belongs to; None when it is unknown or expired."""
        response = httpx.get(
            f"{self.internal_url}/session",
            headers={SSOConfig.SESSION_HEADER: token},
            timeout=SSOConfig.LOOKUP_TIMEOUT_SECONDS,
        )
        if response.status_code == 401:
            return None
        response.raise_for_status()
        return response.json()

    def user(self) -> dict[str, Any] | None:
        token = st.context.cookies.get(SSOConfig.COOKIE_NAME)
        if not token:
            return None
        cached = st.session_state.get(CACHE_KEY)
        if cached and cached["token"] == token and time.monotonic() - cached["checked"] < SSOConfig.RECHECK_SECONDS:
            return cached["user"]
        try:
            user = self.lookup(token)
        except httpx.HTTPError:
            # Sentia briefly unreachable: keep a session confirmed earlier, never invent one.
            return cached["user"] if cached and cached["token"] == token else None
        st.session_state[CACHE_KEY] = {"token": token, "user": user, "checked": time.monotonic()}
        return user

    # Addresses

    @staticmethod
    def here() -> str:
        """This app's address without query or fragment, to come back to after signing in or out.

        Behind a TLS-terminating proxy such as a Cloudflare tunnel, Streamlit sees plain
        HTTP; the proxy's X-Forwarded-Proto and X-Forwarded-Host give the public address.
        """
        parts = urlsplit(st.context.url or "")
        headers = st.context.headers
        scheme = headers.get("X-Forwarded-Proto", "").split(",")[0].strip() or parts.scheme
        host = headers.get("X-Forwarded-Host", "").split(",")[0].strip() or parts.netloc
        return urlunsplit((scheme, host, parts.path or "/", "", ""))

    def login_url(self) -> str:
        return f"{self.public_url}/login?next={quote(self.here(), safe='')}"

    def logout_url(self) -> str:
        return f"{self.public_url}/logout?next={quote(self.here(), safe='')}"

    # Rendering

    @staticmethod
    def sign_out() -> None:
        """Button callback: the next run sends the browser to Sentia's sign-out."""
        st.session_state[SIGN_OUT_KEY] = True

    @staticmethod
    def go(url: str) -> None:
        """Send this browser tab to ``url`` and stop the script."""
        st.markdown(f'<meta http-equiv="refresh" content="0;url={html.escape(url)}">', unsafe_allow_html=True)
        st.stop()

    @staticmethod
    def sign_in_link(url: str) -> None:
        logo = base64.b64encode(GOOGLE_LOGO.encode()).decode("ascii")
        st.markdown(
            f"""<style>
.luna-sso-button {{display:inline-flex;align-items:center;justify-content:center;gap:.65rem;padding:.55rem 1.1rem;
border-radius:.5rem;border:1px solid rgba(255,255,255,.34);background:#f5f5f5;color:#202124!important;
text-decoration:none!important;font-weight:600}}
.luna-sso-button:hover {{background:#e8e8e8}}
.luna-sso-button::before {{content:"";width:1.25rem;height:1.25rem;background:url("data:image/svg+xml;base64,{logo}") center/contain no-repeat}}
</style><a class="luna-sso-button" href="{html.escape(url)}" target="_self">Continue with Google</a>""",
            unsafe_allow_html=True,
        )

    def require_login(self, app_name: str, subtitle: str) -> dict[str, Any]:
        """Return the signed-in, allowed user, or show the sign-in page and stop."""
        if st.session_state.pop(SIGN_OUT_KEY, False):
            st.session_state.pop(CACHE_KEY, None)
            self.go(self.logout_url())
        user = self.user()
        if user is None:
            st.title(app_name)
            st.caption(subtitle)
            self.sign_in_link(self.login_url())
            st.caption("One sign-in opens every Luna app.")
            st.stop()
        if not self.is_allowed(user):
            st.error(f"{user.get('email', 'This account')} is not authorized to access {app_name}.")
            st.button("Sign out", on_click=self.sign_out)
            st.stop()
        return user
