"""Order the visible library so tracks that sound alike sit together."""

import logging
from typing import Any

import numpy as np

from app.data.repositories import TrackRepository

logger = logging.getLogger(__name__)


class ShowcaseSorter:
    """Save an embedding-similarity order for the visible library, or go back to newest first.

    Similarity is the cosine of two tracks' CLAP embeddings. The order starts
    from ``start`` (default: the newest embedded track), always steps to the
    most similar remaining track, then reverses stretches of the path while
    that raises the total neighbor similarity (2-opt), so alike tracks form
    runs instead of scattering. Tracks still without an embedding stay
    unranked and show first until a backfill embeds them and the next sort.
    """

    MAX_SMOOTHING_PASSES = 8
    SAMPLE_SIZE = 12

    def __init__(self, tracks: TrackRepository) -> None:
        self.tracks = tracks

    def sort(self, order: str, start: str | None = None) -> dict[str, Any]:
        if order == "newest":
            cleared = self.tracks.clear_showcase_order()
            return {"status": "sorted", "order": "newest", "track_count": cleared}
        if order != "similarity":
            raise ValueError('order must be "similarity" or "newest".')
        rows = self.tracks.showcase_candidates()
        embedded = [row for row in rows if row["embedding"]]
        missing = [row["name"] for row in rows if not row["embedding"]]
        if not embedded:
            raise ValueError("No visible track has an embedding yet; run backfill_metadata first.")
        names = [row["name"] for row in embedded]
        if start is not None and start not in names:
            raise FileNotFoundError(f"Track {start!r} is not a visible track with an embedding.")
        similarity = self.similarity_matrix(np.asarray([row["embedding"] for row in embedded]))
        path = self.smoothed(self.greedy_path(similarity, names.index(start) if start else 0), similarity)
        ordered = [names[index] for index in path]
        self.tracks.save_showcase_order(ordered)
        result = {
            "status": "sorted",
            "order": "similarity",
            "track_count": len(ordered),
            "start": ordered[0],
            "first_tracks": ordered[: self.SAMPLE_SIZE],
        }
        if missing:
            result["unranked_without_embedding"] = missing
            result["hint"] = "These show first; run backfill_metadata to embed them, then sort again."
        return result

    def place(self, name: str) -> None:
        """Slot a newly visible track into the saved order, between its most similar neighbors.

        Nothing changes while the library is newest first, or for a track that
        has no embedding. Placing costs one comparison per ranked track, so
        arrivals stay fast; the order drifts a little from a full sort over
        time. Failures are logged, never raised: the track then shows first.
        """
        try:
            self._place(name)
        except Exception:
            logger.exception("Could not place %r in the showcase order", name)

    def _place(self, name: str) -> None:
        rows = self.tracks.showcase_candidates()
        ranked = sorted(
            (row for row in rows if row["showcase_rank"] is not None and row["embedding"]),
            key=lambda row: row["showcase_rank"],
        )
        arrival = next(
            (row for row in rows if row["name"] == name and row["showcase_rank"] is None and row["embedding"]),
            None,
        )
        if not ranked or arrival is None:
            return
        vectors = self.unit(np.asarray([row["embedding"] for row in ranked]))
        to_new = vectors @ self.unit(np.asarray([arrival["embedding"]]))[0]
        between = np.einsum("ij,ij->i", vectors[:-1], vectors[1:])
        # Inserting at position p puts the track before ranked[p]; between two tracks it
        # gains its two new neighbors and loses the link that joined them.
        gains = np.concatenate(([to_new[0]], to_new[:-1] + to_new[1:] - between, [to_new[-1]]))
        position = int(np.argmax(gains))
        count = len(ranked)
        rank = ranked[position]["showcase_rank"] if position < count else ranked[-1]["showcase_rank"] + 1
        self.tracks.insert_showcase_rank(name, rank)

    @staticmethod
    def unit(embeddings: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / np.where(norms == 0, 1, norms)

    @classmethod
    def similarity_matrix(cls, embeddings: np.ndarray) -> np.ndarray:
        """Cosine similarity of every pair, in one matrix product."""
        unit = cls.unit(embeddings)
        return unit @ unit.T

    @staticmethod
    def greedy_path(similarity: np.ndarray, start: int) -> list[int]:
        size = len(similarity)
        visited = np.zeros(size, dtype=bool)
        path = [start]
        visited[start] = True
        for _ in range(size - 1):
            scores = np.where(visited, -np.inf, similarity[path[-1]])
            # argmax takes the first best, i.e. the newer track, so the result is stable.
            nearest = int(np.argmax(scores))
            path.append(nearest)
            visited[nearest] = True
        return path

    @classmethod
    def smoothed(cls, path: list[int], similarity: np.ndarray) -> list[int]:
        """Reverse stretches of the path (2-opt) while that raises the total neighbor similarity."""
        size = len(path)
        for _ in range(cls.MAX_SMOOTHING_PASSES):
            improved = False
            for i in range(1, size - 1):
                for j in range(i + 1, size):
                    before = similarity[path[i - 1], path[i]]
                    after = similarity[path[i - 1], path[j]]
                    if j + 1 < size:
                        before += similarity[path[j], path[j + 1]]
                        after += similarity[path[i], path[j + 1]]
                    if after > before + 1e-9:
                        path[i : j + 1] = reversed(path[i : j + 1])
                        improved = True
            if not improved:
                break
        return path
