"""Typed access to the Streamlit session state shared across Luna Vibia views."""

from typing import Any

import streamlit as st


class SessionState:
    """Own session-state defaults and the cross-view state transitions."""

    DEFAULTS: dict[str, Any] = {
        "color_theme": "dark",
        "gallery_view_mode": "grid",
        "saved_uploads": set,
        "uploaded_tracks": list,
        "failed_uploads": dict,
        "uploader_key": 0,
        "view_generation": 0,
        "view_selector_generations": dict,
        "view_page": 0,
        "pending_view_delete": None,
        "pending_view_hide": None,
        "gallery_transitions": dict,
    }

    @classmethod
    def initialize(cls) -> None:
        """Seed every default once; mutable defaults are built fresh per session."""
        for key, default in cls.DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = default() if callable(default) else default

    @staticmethod
    def is_list_view() -> bool:
        return st.session_state.gallery_view_mode == "list"

    @staticmethod
    def set_gallery_view(mode: str) -> None:
        st.session_state.gallery_view_mode = mode

    @staticmethod
    def refresh_gallery() -> None:
        """Recreate gallery widgets after the underlying track set changed."""
        st.session_state.view_generation += 1

    @staticmethod
    def request_delete(name: str) -> None:
        st.session_state.pending_view_hide = None
        st.session_state.pending_view_delete = name

    @staticmethod
    def request_hide(name: str) -> None:
        st.session_state.pending_view_delete = None
        st.session_state.pending_view_hide = name

    @staticmethod
    def clear_pending_actions(valid_names: set[str] | None = None) -> None:
        """Drop pending delete/hide requests whose track is no longer listed."""
        for key in ("pending_view_delete", "pending_view_hide"):
            if valid_names is None or st.session_state[key] not in valid_names:
                st.session_state[key] = None

    @staticmethod
    def forget_upload(name: str) -> None:
        """Let a deleted track be uploaded again in this session."""
        retained = []
        for track in st.session_state.uploaded_tracks:
            if track["name"] == name:
                st.session_state.saved_uploads.discard(track["upload_id"])
            else:
                retained.append(track)
        st.session_state.uploaded_tracks = retained

    @staticmethod
    def bump_selector(name: str) -> None:
        """Remount one thumbnail selector so it can be clicked again."""
        generations = dict(st.session_state.view_selector_generations)
        generations[name] = generations.get(name, 0) + 1
        st.session_state.view_selector_generations = generations

    @staticmethod
    def selector_generation(name: str) -> int:
        return st.session_state.view_selector_generations.get(name, 0)
