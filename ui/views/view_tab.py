"""View Tracks tab: the searchable visible-track gallery."""

from services.tracks import TrackCollection
from views.actions import GalleryActions
from views.gallery import TrackGallery
from views.shared import SearchFilter, VibiaTab


class ViewTab(VibiaTab):
    def render(self) -> None:
        collection = SearchFilter(
            self.layout,
            key="view_name_search",
            label="Search by track name",
            no_match_message="No filenames or tags match your search.",
        ).apply(TrackCollection.visible(self.api, self.files))
        if collection is not None:
            TrackGallery(self.context, GalleryActions(self.api)).render(collection)
