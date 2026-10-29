import unittest

from views.playback_bar import PlaybackBar


class PlaybackBarTests(unittest.TestCase):
    SPINX = {"name": "Stone Spinx Pro", "description": "Bluetooth Speakers (Stone Spinx Pro)"}

    def test_playing_names_the_track_and_the_live_speaker(self):
        text = PlaybackBar.describe({
            "status": "playing", "now_playing": "rain_<b>.wav", "output": self.SPINX,
            "requested_speaker": {"name": "Echo Dot-PL7", "description": "Speakers (Echo Dot-PL7)"},
        })
        self.assertIn("rain_&lt;b&gt;.wav", text)
        self.assertIn("on <strong>Bluetooth Speakers (Stone Spinx Pro)</strong>", text)
        self.assertIn("switched from Speakers (Echo Dot-PL7)", text)

    def test_idle_shows_the_current_speaker(self):
        self.assertEqual(
            PlaybackBar.describe({"status": "idle", "output": self.SPINX}),
            "Speaker: <strong>Bluetooth Speakers (Stone Spinx Pro)</strong>",
        )

    def test_unreachable_speakers_explain_why(self):
        text = PlaybackBar.describe({"status": "idle", "output": None, "output_error": "helper down"})
        self.assertEqual(text, "Speaker unavailable: helper down")
        self.assertIsNone(PlaybackBar.describe({"status": "idle", "output": None}))


if __name__ == "__main__":
    unittest.main()
