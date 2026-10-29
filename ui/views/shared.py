"""Shared Streamlit building blocks for the Luna Vibia tabs."""

import html
from dataclasses import dataclass

import streamlit as st

from services.api import LunaVibiaAPI
from config import UIConfig
from services.tracks import TrackCollection, TrackFiles
from services.state import SessionState


class ResponsiveLayout:
    """Adapt gallery density and copy to phone, tablet, or desktop browsers."""

    MOBILE_TOKENS = ("android", "iphone", "ipad", "ipod", "mobile")

    def __init__(self, config: UIConfig) -> None:
        self.config = config

    @classmethod
    def is_mobile(cls) -> bool:
        user_agent = st.context.headers.get("User-Agent", "").casefold()
        return any(token in user_agent for token in cls.MOBILE_TOKENS)

    def gallery_columns(self) -> int:
        """Use one column in list view or on mobile, otherwise the configured count."""
        if SessionState.is_list_view() or self.is_mobile():
            return 1
        return self.config.gallery_columns

    def search_placeholder(self) -> str:
        return "Name or tag" if self.is_mobile() else "Search by filename or tag"


@dataclass(frozen=True)
class VibiaContext:
    """Dependencies every tab, gallery, and dialog needs."""

    api: LunaVibiaAPI
    config: UIConfig
    files: TrackFiles
    layout: ResponsiveLayout

    @classmethod
    def create(cls, config: UIConfig) -> "VibiaContext":
        return cls(LunaVibiaAPI(config), config, TrackFiles(config), ResponsiveLayout(config))


class TrackLabel:
    """A single-line, truncated filename with its full value as a tooltip."""

    @staticmethod
    def render(container, stored_name: str) -> None:
        display_name = html.escape(TrackFiles.display_name(stored_name), quote=True)
        container.markdown(
            f"""<div title="{display_name}" style="
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                color: var(--lv-muted);
                font-size: 0.875rem;
                line-height: 1.25rem;
                margin-bottom: 0.25rem;
            ">{display_name}</div>""",
            unsafe_allow_html=True,
        )


class SearchFilter:
    """A filename/tag search box that narrows a track collection."""

    def __init__(
        self, layout: ResponsiveLayout, key: str, label: str, no_match_message: str
    ) -> None:
        self.layout = layout
        self.key = key
        self.label = label
        self.no_match_message = no_match_message

    def apply(self, collection: TrackCollection) -> TrackCollection | None:
        """Return the matches, or None after reporting that a query matched nothing."""
        query = (
            st.text_input(
                self.label,
                placeholder=self.layout.search_placeholder(),
                key=self.key,
                icon=":material/search:",
                label_visibility="collapsed",
            )
            .strip()
            .casefold()
        )
        filtered = collection.matching(query)
        if query and not filtered.tracks:
            st.info(self.no_match_message)
            return None
        return filtered


class VibiaTab:
    """Base class giving every tab its shared dependencies."""

    def __init__(self, context: VibiaContext) -> None:
        self.context = context
        self.api = context.api
        self.files = context.files
        self.layout = context.layout

    def render(self) -> None:
        raise NotImplementedError
