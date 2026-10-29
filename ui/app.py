"""Luna Vibia Streamlit application entry point."""

import base64
import hashlib
import inspect
from pathlib import Path

import streamlit as st
from PIL import Image

from sso import LunaSingleSignOn
from config import UIConfig
from services.state import SessionState
from styles import LunaStyle
from views.favorites_tab import FavoritesTab
from views.hidden_tab import HiddenTab
from views.shared import VibiaContext
from views.upload_dialog import UploadDialog
from views.view_tab import ViewTab


class GalleryNavigation:
    """The full-width segmented control that selects a gallery section."""

    SECTION_KEY = "gallery-section"
    LAST_SECTION_KEY = "gallery-section-last"
    DEFAULT_SECTION = "view"
    SECTIONS = {
        "view": (":material/visibility: View Tracks", ViewTab),
        "favorites": (":material/star: Favorite Tracks", FavoritesTab),
        "hidden": (":material/lock: Hidden Tracks", HiddenTab),
    }

    @classmethod
    def _last_section(cls) -> str:
        return st.session_state.get(cls.LAST_SECTION_KEY, cls.DEFAULT_SECTION)

    @classmethod
    def _preserve_selection(cls) -> None:
        """Retain the last section when the already-active segment is clicked."""
        selected = st.session_state.get(cls.SECTION_KEY)
        if selected is None:
            st.session_state[cls.SECTION_KEY] = cls._last_section()
        else:
            st.session_state[cls.LAST_SECTION_KEY] = selected

    @classmethod
    def render(cls) -> type:
        """Render the navigation and return the selected tab class."""
        options = {
            "options": list(cls.SECTIONS),
            "format_func": lambda section: cls.SECTIONS[section][0],
            "key": cls.SECTION_KEY,
            "on_change": cls._preserve_selection,
            "label_visibility": "collapsed",
        }
        if cls.SECTION_KEY not in st.session_state:
            options["default"] = cls.DEFAULT_SECTION
        if "width" in inspect.signature(st.segmented_control).parameters:
            options["width"] = "stretch"
        container = st.container(key="gallery_navigation")
        active = st.session_state.get(cls.SECTION_KEY, cls._last_section())
        container.markdown(f'<span class="lv-selected-{active}"></span>', unsafe_allow_html=True)
        selected = container.segmented_control("Gallery section", **options)
        return cls.SECTIONS[selected or cls._last_section()][1]


class LunaVibiaApp:
    """Compose and render the Luna Vibia Streamlit interface."""

    def __init__(self) -> None:
        self.config = UIConfig.from_env()
        self.context = VibiaContext.create(self.config)

    @staticmethod
    def source_revision() -> str:
        """Hash the UI sources so a live-synced code change can be announced."""
        source_root = UIConfig.UI_ROOT
        source_files = sorted(source_root.rglob("*.py"))
        source_files.extend([source_root / ".streamlit" / "config.toml", UIConfig.LOGO_PATH])
        digest = hashlib.sha256()
        for source_file in source_files:
            if source_file.is_file():
                digest.update(source_file.relative_to(source_root).as_posix().encode())
                digest.update(source_file.read_bytes())
        return digest.hexdigest()

    @classmethod
    def show_reload_notice(cls) -> None:
        revision = cls.source_revision()
        previous_revision = st.session_state.get("ui_source_revision")
        st.session_state.ui_source_revision = revision
        if previous_revision is not None and previous_revision != revision:
            st.toast("Luna Vibia updated", icon=":material/refresh:")

    @staticmethod
    def logo_markup(logo_path: Path) -> str:
        logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        return f'<img class="lv-mark" src="data:image/png;base64,{logo_data}" alt="Luna Vibia logo">'

    def render_header(self) -> bool:
        """Render the branded header and view controls; return True to open uploads.

        Nothing that creates a layout block may render before this header; see
        UI_STYLE_GUIDE.md ("Header-position invariant").
        """
        view_mode = st.session_state.gallery_view_mode
        brand_column, buttons_column = st.columns([5, 4], vertical_alignment="center", gap="medium")
        with brand_column:
            st.markdown(
                f"""
                <div class="lv-header">
                    {self.logo_markup(UIConfig.LOGO_PATH)}
                    <div>
                        <h1 class="lv-title">Luna Vibia</h1>
                        <p class="lv-subtitle">Private AI-managed music library</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with buttons_column:
            grid_column, list_column, upload_column, sign_out_column = st.columns(
                [1, 1, 3, 2], vertical_alignment="center", gap="small"
            )
            for column, mode, icon, label in (
                (grid_column, "grid", ":material/grid_view:", "Grid view"),
                (list_column, "list", ":material/view_list:", "List view"),
            ):
                column.button(
                    icon,
                    type="primary" if view_mode == mode else "secondary",
                    key=f"use_{mode}_view",
                    on_click=SessionState.set_gallery_view,
                    args=(mode,),
                    width="stretch",
                )
            open_upload = upload_column.button(
                "Upload Tracks",
                icon=":material/upload:",
                type="primary",
                key="open_upload_dialog",
                width="stretch",
            )
            sign_out_column.button(
                "Sign out",
                icon=":material/logout:",
                key="header_sign_out",
                on_click=LunaSingleSignOn.sign_out,
                width="stretch",
            )
            return open_upload

    def render(self) -> None:
        SessionState.initialize()
        self.show_reload_notice()
        LunaStyle.apply(st.session_state.color_theme)
        LunaSingleSignOn(self.config.allowed_emails, self.config.sso).require_login(
            "Luna Vibia", "Private AI-managed music library"
        )
        open_upload = self.render_header()
        if open_upload:
            UploadDialog(self.context).open()
        GalleryNavigation.render()(self.context).render()

    @classmethod
    def run(cls) -> None:
        st.set_page_config(
            page_title="Luna Vibia",
            page_icon=Image.open(UIConfig.LOGO_PATH),
            layout="wide",
            initial_sidebar_state="collapsed",
        )
        cls().render()


if __name__ == "__main__":
    LunaVibiaApp.run()
