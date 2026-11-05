"""The speakers are in the owner's home: nobody else plays on them or sees what plays."""

import unittest
from unittest import mock

from app.core import tenancy
from app.integrations.speakers import OwnerSpeakers


class OwnerSpeakerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = mock.Mock()
        self.player.status.return_value = {"status": "playing", "now_playing": "secret.wav"}
        self.player.live_status.return_value = {"status": "playing", "now_playing": "secret.wav"}
        self.player.speakers.return_value = ["lounge"]
        self.speakers = OwnerSpeakers(self.player)

    def test_others_see_nothing_playing_and_no_speakers(self) -> None:
        with tenancy.acting_as("ab12"):
            self.assertEqual(self.speakers.status()["status"], "idle")
            self.assertIsNone(self.speakers.live_status()["now_playing"])
            self.assertEqual(self.speakers.speakers(), [])

    def test_others_cannot_change_anything(self) -> None:
        with tenancy.acting_as("ab12"):
            for call in (
                lambda: self.speakers.play([], "lounge", False),
                lambda: self.speakers.switch("lounge"),
                self.speakers.stop,
                self.speakers.volume,
                lambda: self.speakers.set_volume(50),
                self.speakers.repair_audio,
                self.speakers.audio_repair_status,
            ):
                with self.assertRaises(PermissionError):
                    call()
        self.player.play.assert_not_called()
        self.player.stop.assert_not_called()
        self.player.set_volume.assert_not_called()
        self.player.repair_audio.assert_not_called()

    def test_the_owner_uses_them_as_before(self) -> None:
        with tenancy.acting_as(tenancy.OWNER):
            self.assertEqual(self.speakers.status()["now_playing"], "secret.wav")
            self.speakers.stop()
        self.player.stop.assert_called_once()
