"""Paginated galleries with an animated page-change transition."""

import time
from pathlib import Path

import streamlit as st


class GalleryPager:
    """Slice a gallery into pages and drive the exit/enter page animation.

    A page change is queued as an ``out`` transition so the current grid can
    animate away; ``finish_transition`` then swaps the page and reruns for the
    ``in`` animation.
    """

    # Keep the old grid through its 160 ms exit plus a 50 ms pause.
    EXIT_SECONDS = 0.21

    def __init__(self, tracks_per_page: int, state_key: str) -> None:
        self.tracks_per_page = tracks_per_page
        self.state_key = state_key

    @staticmethod
    def _transitions() -> dict:
        return st.session_state.gallery_transitions

    def page_count(self, tracks: list[Path]) -> int:
        return (len(tracks) + self.tracks_per_page - 1) // self.tracks_per_page

    def current_page(self, page_count: int) -> int:
        """Clamp and persist the active page index."""
        page = min(max(st.session_state[self.state_key], 0), page_count - 1)
        st.session_state[self.state_key] = page
        return page

    def reset(self) -> None:
        st.session_state[self.state_key] = 0

    def paginate(self, tracks: list[Path]) -> tuple[int, list[Path]]:
        """Return the bounded page index and the tracks on that page."""
        page = self.current_page(self.page_count(tracks))
        start = page * self.tracks_per_page
        return page, tracks[start : start + self.tracks_per_page]

    def phase(self) -> str:
        transition = self._transitions().get(self.state_key)
        return transition["phase"] if transition else "idle"

    def render_transition_marker(self) -> None:
        """Mark this rerun for the gallery's scoped CSS animation."""
        st.markdown(
            f'<span class="lv-gallery-transition lv-gallery-{self.phase()}"></span>',
            unsafe_allow_html=True,
        )

    def _queue(self, target_page: int) -> None:
        self._transitions()[self.state_key] = {"phase": "out", "target": target_page}

    def _change_page(self, selector_key: str, target_page: int) -> None:
        self._queue(target_page)
        st.session_state[selector_key] = target_page + 1

    def _sync_page(self, selector_key: str) -> None:
        target_page = st.session_state[selector_key] - 1
        if target_page != st.session_state[self.state_key]:
            self._queue(target_page)

    def render_footer(self, tracks: list[Path], key_prefix: str) -> None:
        """Render previous/next buttons and a page selector beneath the gallery."""
        page_count = self.page_count(tracks)
        key_prefix = f"{key_prefix}_{page_count}"
        current_page = self.current_page(page_count)
        selector_key = f"{key_prefix}_page"
        exiting = self.phase() == "out"

        previous_column, page_column, next_column = st.columns([2, 7, 2])
        previous_column.markdown('<span class="lv-pagination"></span>', unsafe_allow_html=True)
        previous_column.button(
            ":material/arrow_back:",
            disabled=exiting or current_page == 0,
            width="stretch",
            key=f"{key_prefix}_previous",
            on_click=self._change_page,
            args=(selector_key, current_page - 1),
        )
        # Callbacks update state before Streamlit instantiates the next rerun.
        page_column.selectbox(
            "Page",
            options=list(range(1, page_count + 1)),
            format_func=lambda page: f"Page {page} of {page_count}",
            index=current_page,
            label_visibility="collapsed",
            disabled=exiting,
            key=selector_key,
            on_change=self._sync_page,
            args=(selector_key,),
        )
        next_column.button(
            ":material/arrow_forward:",
            disabled=exiting or current_page == page_count - 1,
            width="stretch",
            key=f"{key_prefix}_next",
            on_click=self._change_page,
            args=(selector_key, current_page + 1),
        )

    def finish_transition(self) -> None:
        """After the exit animation, swap to the target page and rerun to enter."""
        transition = self._transitions().get(self.state_key)
        if not transition:
            return
        if transition["phase"] == "out":
            # The old grid's deltas are already emitted; keep it mounted for the exit.
            time.sleep(self.EXIT_SECONDS)
            st.session_state[self.state_key] = transition["target"]
            transition["phase"] = "in"
            st.rerun()
        self._transitions().pop(self.state_key, None)
