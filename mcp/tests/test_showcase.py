import unittest

from fakes import FakeTrackRepository
from app.services.showcase import ShowcaseSorter

LOW, LOWER, HIGH, HIGHER = [1.0, 0.1, 0.0], [0.9, 0.4, 0.0], [0.0, 0.1, 1.0], [0.0, 0.5, 0.8]


class ShowcaseSorterTests(unittest.TestCase):
    """Tracks with alike embeddings end up next to each other; newest-first comes back on request."""

    TRACKS = {  # name: embedding, oldest first
        "low_1.wav": LOW,
        "high_1.wav": HIGH,
        "low_2.wav": LOWER,
        "high_2.wav": HIGHER,
        "low_3.wav": LOW,
    }

    def setUp(self) -> None:
        self.repository = FakeTrackRepository()
        for name, embedding in self.TRACKS.items():
            self.add(name, embedding)
        self.sorter = ShowcaseSorter(self.repository)

    def add(self, name: str, embedding: list[float] | None) -> None:
        self.repository.rows[name] = {"name": name, "embedding": embedding, "hidden": False, "favorite": False}

    def library(self) -> list[str]:
        return [row["name"] for row in self.repository.list()]

    def test_similarity_groups_alike_tracks_from_the_newest(self) -> None:
        result = self.sorter.sort("similarity")
        order = self.library()
        self.assertEqual((result["track_count"], result["start"], order[0]), (5, "low_3.wav", "low_3.wav"))
        self.assertEqual(set(order[:3]), {"low_1.wav", "low_2.wav", "low_3.wav"})
        self.assertEqual(set(order[3:]), {"high_1.wav", "high_2.wav"})

    def test_start_track_and_tracks_without_embeddings(self) -> None:
        self.add("pending.wav", None)
        result = self.sorter.sort("similarity", start="high_1.wav")
        self.assertEqual(result["unranked_without_embedding"], ["pending.wav"])
        self.assertEqual(self.library()[:3], ["pending.wav", "high_1.wav", "high_2.wav"])
        with self.assertRaises(FileNotFoundError):
            self.sorter.sort("similarity", start="pending.wav")

    def test_newest_clears_the_saved_order(self) -> None:
        self.sorter.sort("similarity")
        self.assertEqual(self.sorter.sort("newest")["track_count"], 5)
        self.assertEqual(self.library(), list(self.TRACKS))

    def test_arrival_is_placed_beside_its_closest_neighbors(self) -> None:
        self.sorter.sort("similarity")
        self.add("high_3.wav", HIGH)
        self.sorter.place("high_3.wav")
        order = self.library()
        self.assertEqual(set(order[-3:]), {"high_1.wav", "high_2.wav", "high_3.wav"})

    def test_placing_does_nothing_while_newest_first(self) -> None:
        self.add("new.wav", LOW)
        self.sorter.place("new.wav")
        self.assertIsNone(self.repository.rows["new.wav"].get("showcase_rank"))

    def test_unknown_order_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.sorter.sort("random")
