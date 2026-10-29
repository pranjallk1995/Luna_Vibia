"""Favorites tab: the View Tracks gallery limited to favorite tracks."""

from services.tracks import TrackCollection
from views.actions import FavoriteActions
from views.gallery import TrackGallery
from views.shared import SearchFilter, VibiaTab


class FavoritesTab(VibiaTab):
    def render(self) -> None:
        actions = FavoriteActions(self.api)
        favorites = TrackCollection.visible(self.api, self.files).only(actions.favorite_names())
        collection = SearchFilter(
            self.layout,
            key="favorite_name_search",
            label="Search Favorites by track name",
            no_match_message="No favorite filenames or tags match your search.",
        ).apply(favorites)
        if collection is not None:
            TrackGallery(self.context, actions).render(collection)
