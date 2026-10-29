"""Hidden Tracks tab for the OAuth-authenticated Luna Vibia user."""

from services.api import LunaVibiaAPI
from services.tracks import TrackCollection
from views.actions import HiddenActions
from views.gallery import TrackGallery
from views.shared import SearchFilter, VibiaTab


class HiddenTab(VibiaTab):
    def render(self) -> None:
        collection = SearchFilter(
            self.layout,
            key="hidden_name_search",
            label="Search hidden vault by track name",
            no_match_message="No hidden filenames or tags match your search.",
        ).apply(TrackCollection.from_metadata(self.files, self.api.hidden_tracks()))
        if collection is not None:
            TrackGallery(self.context, HiddenActions(self.api)).render(collection)
