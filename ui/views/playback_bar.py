"""A live line under the header: what Vibia plays on the host's speakers, and where."""

import html

import httpx
import streamlit as st

from config import UIConfig
from services.api import LunaVibiaAPI


class PlaybackBar:
    """Show the speaker sound reaches now, refreshed while the page is open.

    The backend reads the output live, so a speaker Windows switched to on its
    own (for example one that just connected) shows here too.
    """

    def __init__(self, api: LunaVibiaAPI) -> None:
        self.api = api

    @staticmethod
    def describe(status: dict) -> str | None:
        """The bar's text as HTML, or None when there is nothing to show."""
        output = status.get("output")
        where = html.escape(output["description"]) if output else None
        if status.get("status") == "playing":
            track = html.escape(status.get("now_playing") or "")
            text = f"Playing <strong>{track}</strong>"
            if where:
                text += f" on <strong>{where}</strong>"
            requested = status.get("requested_speaker")
            if requested:
                text += f" (Windows switched from {html.escape(requested['description'])})"
            return text
        if status.get("status") == "failed":
            return f"Playback stopped: {html.escape(status.get('error', 'unknown error'))}"
        if where:
            return f"Speaker: <strong>{where}</strong>"
        if status.get("output_error"):
            return f"Speaker unavailable: {html.escape(status['output_error'])}"
        return None

    @st.fragment(run_every=UIConfig.PLAYBACK_REFRESH_SECONDS)
    def render(self) -> None:
        try:
            status = self.api.playback()
        except httpx.HTTPError:
            return
        text = self.describe(status)
        if text:
            st.markdown(
                f'<p class="lv-playback"><span class="lv-playback-icon">&#128264;</span>{text}</p>',
                unsafe_allow_html=True,
            )
