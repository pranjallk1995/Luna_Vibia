"""Tests for the Luna Vibia track use cases."""

import base64
import tempfile
import textwrap
import unittest
from pathlib import Path

from fakes import (
    FakeCaptioner,
    FakeEncoder,
    FakePublicURLRepository,
    FakeTrackRepository,
    FakeVisia,
    encoded,
    wav_bytes,
    wav_payload,
)

from app.core.config import AppConfig
from app.core.models import MetadataChange, MetadataRules
from app.integrations.visia import VisiaImageCatalog
from app.services.application import VibiaService
from app.services.inspection import TrackInspector
from app.services.uploads import UploadLinkNotFound


class VibiaServiceTestCase(unittest.TestCase):
    """Build a real service graph over in-memory repositories and fake models."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.downloads_temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = FakeTrackRepository()
        self.config = AppConfig(
            track_dir=self.root,
            database_url="postgresql://test",
            ollama_url="http://ollama:11434",
            caption_model="test-caption",
            public_base_url="https://vault.example.test/vault",
            download_dir=Path(self.downloads_temp.name),
        )
        self.captioner = FakeCaptioner()
        self.encoder = FakeEncoder()
        self.service = VibiaService.create(
            self.config,
            self.repository,
            FakePublicURLRepository(self.repository),
            self.captioner,
            self.encoder,
            FakeVisia(),
        )
        self.visible = self.service.visible
        self.hidden = self.service.hidden

    def tearDown(self):
        self.temp.cleanup()
        self.downloads_temp.cleanup()


class IngestTests(VibiaServiceTestCase):
    def test_ingest_persists_generated_metadata_and_measured_facts(self):
        result = self.visible.ingest("song.wav", wav_payload(440, 3))
        self.assertEqual(result["caption"], "A calm piano piece.")
        self.assertEqual(result["tags"], ["piano", "calm"])
        self.assertEqual(result["audio_format"], "WAV")
        self.assertAlmostEqual(result["duration_seconds"], 3.0, places=1)
        self.assertEqual((result["sample_rate"], result["channels"]), (48000, 1))
        self.assertIsNotNone(result["energy"])
        self.assertTrue((self.root / "song.wav").is_file())
        self.assertEqual(result["public_url"], "https://vault.example.test/vault/api/public/tracks/track-1")
        self.assertEqual(self.repository.rows["song.wav"]["embedding"], FakeEncoder.for_pitch(440))
        self.assertEqual(result["analysis_model"], "test-caption + fake-clap")

    def test_caption_model_is_given_what_was_heard_and_measured(self):
        self.visible.ingest("song.wav", wav_payload())
        facts, heard = self.captioner.calls[-1]
        self.assertEqual(heard["genre"], ["piano solo"])
        self.assertEqual(facts.audio_format, "WAV")

    def test_uploader_notes_title_and_artist_are_stored_and_used(self):
        given = {"title": "Evening Brew", "artist": "Suno", "notes": "lofi piano, warm, 80 bpm"}
        result = self.visible.upload("brew.wav", wav_bytes(), given)
        self.assertEqual(
            (result["title"], result["artist"], result["notes"]), ("Evening Brew", "Suno", "lofi piano, warm, 80 bpm")
        )
        self.assertEqual(result["caption"], "Evening Brew: a calm piano piece.")

    def test_file_tags_fill_title_and_artist(self):
        result = self.visible.upload("tagged.mp3", encoded("mp3", title="Rain Song", artist="Someone"))
        self.assertEqual((result["title"], result["artist"]), ("Rain Song", "Someone"))

    def test_ingest_rejects_existing_name_without_replace(self):
        self.visible.ingest("song.wav", wav_payload())
        with self.assertRaises(FileExistsError):
            self.visible.ingest("song.wav", wav_payload(523))

    def test_ingest_rejects_mismatched_format(self):
        with self.assertRaisesRegex(ValueError, "filename expects MP3"):
            self.visible.ingest("song.mp3", wav_payload())
        self.assertFalse((self.root / "song.mp3").exists())

    def test_ingest_rolls_file_back_when_metadata_persistence_fails(self):
        self.repository.upsert = lambda record, base: (_ for _ in ()).throw(RuntimeError("database unavailable"))
        with self.assertRaises(RuntimeError):
            self.visible.ingest("song.wav", wav_payload())
        self.assertFalse((self.root / "song.wav").exists())

    def test_replacing_track_adds_ai_modified_tag_and_keeps_notes(self):
        self.visible.upload("song.wav", wav_bytes(), {"title": "Morning"})
        result = self.visible.ingest("song.wav", wav_payload(523), replace=True)
        self.assertEqual(result["tags"], ["piano", "calm", "ai modified"])
        self.assertEqual(result["title"], "Morning")

    def test_analysis_graph_measures_then_listens_and_checks_provenance_in_parallel(self):
        graph = self.service.indexer.graph.graph.get_graph()
        self.assertEqual({edge.target for edge in graph.edges if edge.source == "measure"}, {"listen", "check_provenance"})
        self.assertEqual({edge.source for edge in graph.edges if edge.target == "describe"}, {"listen", "check_provenance"})

    def test_backfill_skips_current_records(self):
        self.visible.ingest("song.wav", wav_payload())
        (self.root / "other.wav").write_bytes(wav_bytes(660))
        result = self.service.indexer.backfill()
        self.assertEqual(result["analyzed"], ["other.wav"])
        self.assertEqual(result["skipped_count"], 1)

    def test_backfill_reanalyzes_other_model_records_and_keeps_ai_modified_and_notes(self):
        self.visible.upload("song.wav", wav_bytes(), {"notes": "jazz trio"})
        self.repository.rows["song.wav"]["analysis_model"] = "older-model"
        self.repository.rows["song.wav"]["tags"] = ["piano", "ai modified"]
        result = self.service.indexer.backfill()
        self.assertEqual(result["analyzed"], ["song.wav"])
        row = self.repository.rows["song.wav"]
        self.assertEqual(row["analysis_model"], "test-caption + fake-clap")
        self.assertIn("ai modified", row["tags"])
        self.assertEqual(row["notes"], "jazz trio")


class FormatTests(VibiaServiceTestCase):
    def test_common_formats_are_detected_and_named(self):
        for audio_format, extension in (("mp3", ".mp3"), ("flac", ".flac"), ("ogg", ".ogg"), ("m4a", ".m4a")):
            with self.subTest(audio_format):
                data = encoded(audio_format, hertz=300 + len(audio_format) * 50)
                result = self.visible.upload("clip", data)
                self.assertEqual(result["name"], f"clip{extension}")
                self.assertEqual(result["audio_format"], audio_format.upper())

    def test_unsupported_or_invalid_content_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not a valid audio file"):
            self.visible.upload("notes.mp3", b"hello")
        with self.assertRaisesRegex(ValueError, "empty"):
            self.visible.upload("empty.mp3", b"")


class AIProvenanceTests(VibiaServiceTestCase):
    def test_generator_named_in_tags_is_an_ai_signal(self):
        inspected = TrackInspector().inspect(encoded("mp3", comment="Made with Suno v4"))
        self.assertTrue(inspected["ai_generated"])
        self.assertEqual(inspected["generator"], "Suno")
        self.assertEqual(inspected["embedded_tags"]["comment"], "Made with Suno v4")

    def test_plain_track_has_no_ai_signals(self):
        inspected = TrackInspector().inspect(wav_bytes())
        self.assertFalse(inspected["ai_generated"])
        self.assertEqual(inspected["ai_signals"], [])

    def test_ingesting_ai_track_adds_ai_info_tag(self):
        result = self.visible.upload("gen.mp3", encoded("mp3", comment="udio"))
        self.assertIn("ai info", result["tags"])

    def test_ai_info_tag_cannot_be_removed_from_ai_tracks(self):
        self.visible.upload("gen.mp3", encoded("mp3", comment="udio"))
        with self.assertRaisesRegex(ValueError, "cannot be removed"):
            self.visible.update_metadata("gen.mp3", MetadataChange(remove_tags=["ai info"]))

    def test_metadata_combines_record_and_embedded_details(self):
        self.visible.upload("gen.mp3", encoded("mp3", comment="Suno"))
        metadata = self.visible.metadata("gen.mp3")
        self.assertEqual(metadata["file"]["format"], "MP3")
        self.assertIn("ai info", metadata["tags"])
        self.assertEqual(metadata["embedded_tags"]["comment"], "Suno")
        self.assertEqual(metadata["generator"], "Suno")
        self.assertEqual(metadata["caption"], "A calm piano piece.")
        summary = self.visible.metadata_page(10, 0, 100)["tracks"][0]["embedded"]
        self.assertEqual((summary["format"], summary["generator"]), ("MP3", "Suno"))


class CoverTests(VibiaServiceTestCase):
    def setUp(self):
        super().setUp()
        self.visible.ingest("song.wav", wav_payload())

    def test_cover_is_resolved_against_visia(self):
        url = f"https://visia.lunaapps.fyi/api/public/images/{FakeVisia.VISIBLE_ID.upper()}"
        result = self.visible.set_cover("song.wav", url)
        self.assertEqual(result["cover_url"], f"https://visia.example.test/api/public/images/{FakeVisia.VISIBLE_ID}")

    def test_hidden_or_unknown_visia_images_are_rejected(self):
        for image_id in (FakeVisia.HIDDEN_ID, "00000000-0000-0000-0000-000000000000"):
            with self.subTest(image_id):
                with self.assertRaisesRegex(FileNotFoundError, "No visible Luna Visia image"):
                    self.visible.set_cover("song.wav", f"https://visia.example.test/api/public/images/{image_id}")

    def test_filename_urls_and_data_uris_are_rejected(self):
        for url in ("https://visia.example.test/api/public/images/cat.png", "data:image/png;base64,AAAA"):
            with self.subTest(url):
                with self.assertRaisesRegex(ValueError, "image-ID URL"):
                    self.visible.set_cover("song.wav", url)

    def test_cover_can_be_cleared_and_survives_reanalysis(self):
        self.visible.set_cover("song.wav", f"https://x.test/api/public/images/{FakeVisia.VISIBLE_ID}")
        self.visible.ingest("song.wav", wav_payload(523), replace=True)
        self.assertIsNotNone(self.repository.rows["song.wav"]["cover_url"])
        self.assertIsNone(self.visible.set_cover("song.wav", None)["cover_url"])

    def test_image_id_parsing(self):
        url = f"https://a.test/api/public/images/{FakeVisia.VISIBLE_ID}/"
        self.assertEqual(VisiaImageCatalog.image_id(url), FakeVisia.VISIBLE_ID)

    def test_storing_a_cover_retries_then_reports_visias_answer(self):
        import httpx
        from unittest.mock import patch

        from app.integrations.visia import VisiaUnavailableError

        def reply(status, body):
            return httpx.Response(status, json=body, request=httpx.Request("POST", "http://visia.test"))

        catalog = VisiaImageCatalog("http://visia.test", companion_token="t" * 32)
        answers = [httpx.ReadTimeout("slow"), reply(502, {"error": "restarting"}), reply(201, {"public_url": "u"})]
        with patch("app.integrations.visia.time.sleep"), patch("app.integrations.visia.httpx.post", side_effect=answers) as post:
            self.assertEqual(catalog.store("song_cover", [], {"content_base64": "AAAA"})["public_url"], "u")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": f"Bearer {'t' * 32}"})
        with patch("app.integrations.visia.httpx.post", return_value=reply(400, {"error": "not an image"})):
            with self.assertRaisesRegex(ValueError, "not an image"):
                catalog.store("song_cover", [], {"content_base64": "AAAA"})
        with self.assertRaisesRegex(VisiaUnavailableError, "LUNAVISIA_COMPANION_TOKEN"):
            VisiaImageCatalog("http://visia.test").store("song_cover", [], {"content_base64": "AAAA"})


class SearchAndPlaylistTests(VibiaServiceTestCase):
    def setUp(self):
        super().setUp()
        # Three distinct pitches, plus a near-duplicate of the 440 Hz track.
        for name, hertz, seconds in (("a.wav", 440, 35), ("a_copy.wav", 441, 40), ("b.wav", 600, 35), ("c.wav", 900, 35)):
            self.visible.upload(name, wav_bytes(hertz, seconds))

    def test_search_ranks_by_meaning(self):
        result = self.service.search.search("440 hz mood", None, False, 10, 0)
        self.assertEqual(self.encoder.texts[-1], "440 hz mood")
        self.assertIn(result["results"][0]["name"], {"a.wav", "a_copy.wav"})
        self.assertEqual(result["results"][-1]["name"], "c.wav")
        self.assertEqual(result["count"], 4)

    def test_search_filters_by_length(self):
        result = self.service.search.search("440", None, False, 10, 0, min_seconds=38)
        self.assertEqual([item["name"] for item in result["results"]], ["a_copy.wav"])

    def test_search_needs_a_description_or_tag(self):
        with self.assertRaisesRegex(ValueError, "Provide a description"):
            self.service.search.search("  ", None, False, 10, 0)

    def test_playlist_prefers_variety_over_near_duplicates(self):
        playlist = self.service.playlists.suggest("440", minutes=1)
        names = [track["name"] for track in playlist["tracks"]]
        self.assertEqual(len(names), 2)
        self.assertIn(names[0], {"a.wav", "a_copy.wav"})
        self.assertEqual(names[1], "b.wav")
        self.assertTrue(playlist["loop"])

    def test_short_library_says_to_loop(self):
        playlist = self.service.playlists.suggest("440", minutes=30)
        self.assertIn("loop the playlist", playlist["note"])
        self.assertNotIn("c.wav", [track["name"] for track in playlist["tracks"]])

    def test_playlist_bounds_minutes(self):
        with self.assertRaisesRegex(ValueError, "minutes must be between"):
            self.service.playlists.suggest("calm", minutes=0)


class PublicURLTests(VibiaServiceTestCase):
    def test_public_url_rejects_hidden_tracks(self):
        self.visible.ingest("song.wav", wav_payload())
        self.repository.rows["song.wav"]["hidden"] = True
        with self.assertRaises(PermissionError):
            self.visible.public_url("song.wav")

    def test_public_path_resolves_stable_track_id(self):
        self.visible.ingest("song.wav", wav_payload())
        self.assertEqual(self.visible.public_path("track-1").name, "song.wav")

    def test_public_base_url_update_regenerates_stored_urls(self):
        self.visible.ingest("song.wav", wav_payload())
        result = self.service.urls.update("https://new-device.example.test/vault/")
        self.assertEqual(result["updated_track_count"], 1)
        self.assertEqual(
            self.repository.rows["song.wav"]["public_url"],
            "https://new-device.example.test/vault/api/public/tracks/track-1",
        )

    def test_public_base_url_rejects_non_https_values(self):
        with self.assertRaises(ValueError):
            self.service.urls.update("http://localhost:18005/vault")


class RenameAndRemoveTests(VibiaServiceTestCase):
    def test_remove_deletes_file_and_metadata(self):
        self.visible.ingest("song.wav", wav_payload())
        self.visible.remove("song.wav")
        self.assertFalse((self.root / "song.wav").exists())
        self.assertNotIn("song.wav", self.repository.rows)

    def test_rename_preserves_file_and_metadata(self):
        original = self.visible.ingest("song.wav", wav_payload())
        self.visible.set_favorite(["song.wav"], True)
        result = self.visible.rename("song.wav", "evening_song.wav")
        self.assertEqual(
            (result["status"], result["old_name"], result["name"]), ("renamed", "song.wav", "evening_song.wav")
        )
        self.assertEqual(result["caption"], original["caption"])
        self.assertTrue(result["favorite"])
        self.assertTrue((self.root / "evening_song.wav").is_file())

    def test_rename_rejects_disallowed_names_and_extension_changes(self):
        self.visible.ingest("song.wav", wav_payload())
        for new_name in ("evening song.wav", "evening-song.wav", "song!.wav"):
            with self.subTest(new_name=new_name):
                with self.assertRaisesRegex(ValueError, "only letters, numbers, and underscores"):
                    self.visible.rename("song.wav", new_name)
        with self.assertRaises(ValueError):
            self.visible.rename("song.wav", "song.mp3")
        with self.assertRaises(ValueError):
            self.visible.rename("song.wav", "../song.wav")
        self.assertTrue((self.root / "song.wav").is_file())

    def test_rename_rejects_collision_and_hidden_tracks(self):
        self.visible.ingest("song.wav", wav_payload())
        self.visible.ingest("other.wav", wav_payload(523))
        with self.assertRaises(FileExistsError):
            self.visible.rename("song.wav", "other.wav")
        self.hidden.set_hidden(["song.wav"], True)
        with self.assertRaises(PermissionError):
            self.visible.rename("song.wav", "renamed.wav")

    def test_rename_rolls_file_back_when_metadata_update_fails(self):
        self.visible.ingest("song.wav", wav_payload())
        self.repository.rename = lambda name, new_name: (_ for _ in ()).throw(RuntimeError("database unavailable"))
        with self.assertRaises(RuntimeError):
            self.visible.rename("song.wav", "renamed.wav")
        self.assertTrue((self.root / "song.wav").is_file())
        self.assertFalse((self.root / "renamed.wav").exists())

    def test_remove_restores_file_when_metadata_delete_fails(self):
        self.visible.ingest("song.wav", wav_payload())
        self.repository.delete = lambda name: (_ for _ in ()).throw(RuntimeError("database unavailable"))
        with self.assertRaises(RuntimeError):
            self.visible.remove("song.wav")
        self.assertTrue((self.root / "song.wav").is_file())


class MetadataTests(VibiaServiceTestCase):
    def test_update_metadata_adds_tag_without_reanalysis(self):
        self.visible.ingest("song.wav", wav_payload())
        calls = len(self.captioner.calls)
        result = self.visible.update_metadata("song.wav", MetadataChange(add_tags=["Evening Coffee"]))
        self.assertEqual(result["tags"], ["piano", "calm", "evening coffee"])
        self.assertEqual(len(self.captioner.calls), calls)

    def test_update_metadata_changes_caption_and_removes_tag(self):
        self.visible.ingest("song.wav", wav_payload())
        result = self.visible.update_metadata("song.wav", MetadataChange(caption="A gentle loop.", remove_tags=["calm"]))
        self.assertEqual((result["caption"], result["tags"]), ("A gentle loop.", ["piano"]))

    def test_update_metadata_requires_a_change_and_visibility(self):
        self.visible.ingest("song.wav", wav_payload())
        with self.assertRaisesRegex(ValueError, "Provide a caption"):
            self.visible.update_metadata("song.wav", MetadataChange())
        self.hidden.set_hidden(["song.wav"], True)
        with self.assertRaises(PermissionError):
            self.visible.update_metadata("song.wav", MetadataChange(add_tags=["private"]))
        result = self.hidden.update_metadata("song.wav", MetadataChange(add_tags=["Private"]))
        self.assertEqual(result["tags"], ["piano", "calm", "private"])

    def test_metadata_rules_normalize_and_bound_tags(self):
        rules = MetadataRules(max_tags=2, search_stop_words=frozenset())
        self.assertEqual(rules.normalize_tags(["Jazz!", "jazz", "  Lo   Fi ", "x"]), ["jazz", "lo fi"])
        with self.assertRaises(ValueError):
            rules.normalize_tags(["!!!"])


class HiddenAndFavoriteTests(VibiaServiceTestCase):
    def test_hidden_tracks_are_excluded_and_protected(self):
        self.visible.ingest("song.wav", wav_payload())
        self.hidden.set_hidden(["song.wav"], True)
        self.assertEqual(self.visible.list(), [])
        self.assertEqual(len(self.hidden.list()), 1)
        with self.assertRaises(PermissionError):
            self.visible.path("song.wav")
        self.assertEqual(self.service.search.search("piano", None, False, 50, 0)["count"], 0)

    def test_hidden_remove_deletes_file_and_rejects_visible_tracks(self):
        self.visible.ingest("song.wav", wav_payload())
        self.visible.ingest("public.wav", wav_payload(523))
        self.hidden.set_hidden(["song.wav"], True)
        self.assertEqual(self.hidden.remove("song.wav")["status"], "deleted")
        self.assertFalse((self.root / "song.wav").exists())
        with self.assertRaisesRegex(PermissionError, "Only hidden tracks"):
            self.hidden.remove_many(["public.wav"])

    def test_favorites_are_persisted_and_hidden_tracks_are_excluded(self):
        self.visible.ingest("song.wav", wav_payload())
        result = self.visible.set_favorite(["song.wav"], True)
        self.assertEqual((result["status"], result["names"]), ("favorited", ["song.wav"]))
        self.assertEqual([item["name"] for item in self.visible.favorites()], ["song.wav"])
        self.hidden.set_hidden(["song.wav"], True)
        self.assertEqual(self.visible.favorites(), [])

    def test_stats_summarize_visible_library_only(self):
        self.visible.upload("gen.mp3", encoded("mp3", comment="Suno"))
        self.visible.ingest("song.wav", wav_payload(440, 3))
        self.visible.ingest("song.wav", wav_payload(523, 3), replace=True)
        self.visible.ingest("secret.wav", wav_payload(660))
        self.visible.set_favorite(["song.wav"], True)
        self.visible.set_cover("song.wav", f"https://x.test/api/public/images/{FakeVisia.VISIBLE_ID}")
        self.hidden.set_hidden(["secret.wav"], True)
        stats = self.visible.stats(top_tags=2)
        self.assertEqual(stats["total_tracks"], 2)
        self.assertEqual(stats["favorite_count"], 1)
        self.assertEqual(stats["with_cover_count"], 1)
        self.assertEqual(stats["ai_generated_count"], 1)
        self.assertEqual(stats["ai_modified_count"], 1)
        self.assertEqual(stats["formats"], {"MP3": 1, "WAV": 1})
        self.assertAlmostEqual(stats["total_duration_seconds"], 5.0, delta=0.2)
        self.assertEqual(stats["top_tags"], [{"tag": "piano", "count": 2}, {"tag": "calm", "count": 2}])

    def test_stats_for_empty_library(self):
        stats = self.visible.stats()
        self.assertEqual((stats["total_tracks"], stats["total_size"], stats["total_duration"]), (0, "0 B", "0m 00s"))
        self.assertIsNone(stats["largest_track"])

    def test_human_units(self):
        self.assertEqual(self.visible.human_bytes(1536), "1.5 KiB")
        self.assertEqual(self.visible.human_duration(3725), "1h 02m")
        self.assertEqual(self.visible.human_duration(95), "1m 35s")


class ChatUploadTests(VibiaServiceTestCase):
    def test_tolerant_base64_variants_are_accepted(self):
        raw = wav_bytes()
        standard = base64.b64encode(raw).decode()
        variants = {
            "wrapped": "\n".join(textwrap.wrap(standard, 76)),
            "unpadded": standard.rstrip("="),
            "urlsafe": base64.urlsafe_b64encode(raw).decode(),
            "data_url": f"data:audio/wav;base64,{standard}",
        }
        for index, (label, payload) in enumerate(variants.items()):
            with self.subTest(label):
                self.repository.rows.clear()
                result = self.visible.ingest(f"song_{index}.wav", payload)
                self.assertEqual((self.root / result["name"]).read_bytes(), raw)

    def test_upload_corrects_wrong_or_missing_extension(self):
        cases = [("song.wav", "song.mp3"), ("sunset", "sunset.mp3"), ("/mnt/data/beach.MP3", "beach.MP3")]
        for index, (requested, expected) in enumerate(cases):
            with self.subTest(requested):
                result = self.visible.upload(requested, encoded("mp3", hertz=300 + 100 * index))
                self.assertEqual((result["name"], result["status"]), (expected, "created"))
                self.assertTrue((self.root / expected).is_file())

    def test_upload_without_name_uses_default_and_numbers_taken_names(self):
        self.assertEqual(self.visible.upload(None, wav_bytes())["name"], "track.wav")
        self.assertEqual(self.visible.upload("track.wav", wav_bytes(523))["name"], "track_2.wav")

    def test_upload_reports_requested_name_when_changed(self):
        self.assertEqual(self.visible.upload("song.wav", encoded("mp3"))["requested_name"], "song.wav")

    def test_upload_reports_exact_duplicate_without_second_copy(self):
        data = wav_bytes()
        first = self.visible.upload("song.wav", data)
        again = self.visible.upload("retry.wav", data)
        self.assertEqual((again["status"], again["name"]), ("duplicate", first["name"]))
        self.assertFalse((self.root / "retry.wav").exists())

    def test_hidden_duplicate_is_not_revealed(self):
        data = wav_bytes()
        self.visible.upload("secret.wav", data)
        self.hidden.set_hidden(["secret.wav"], True)
        result = self.visible.upload("public.wav", data)
        self.assertEqual((result["status"], result["name"]), ("created", "public.wav"))


class UploadLinkTests(VibiaServiceTestCase):
    def test_link_is_single_use(self):
        uploads = self.service.uploads
        link = uploads.create_link("song")
        self.assertTrue(link["upload_url"].startswith("https://vault.example.test/vault/api/uploads/"))
        token = link["upload_url"].rsplit("/", 1)[-1]
        result = uploads.receive(token, wav_bytes())
        self.assertEqual((result["status"], result["name"]), ("created", "song.wav"))
        with self.assertRaises(UploadLinkNotFound):
            uploads.receive(token, wav_bytes(523))

    def test_failed_upload_can_retry_on_same_link(self):
        uploads = self.service.uploads
        token = uploads.create_link("song.wav")["upload_url"].rsplit("/", 1)[-1]
        with self.assertRaises(ValueError):
            uploads.receive(token, b"not audio")
        self.assertEqual(uploads.receive(token, wav_bytes())["status"], "created")

    def test_expired_link_is_rejected(self):
        uploads = self.service.uploads
        uploads.store.ttl_seconds = 0
        token = uploads.create_link("song.wav")["upload_url"].rsplit("/", 1)[-1]
        with self.assertRaises(UploadLinkNotFound):
            uploads.receive(token, wav_bytes())

    def test_replace_link_requires_existing_visible_track(self):
        uploads = self.service.uploads
        with self.assertRaises(FileNotFoundError):
            uploads.create_link("missing.wav", replace=True)
        self.visible.ingest("song.wav", wav_payload())
        token = uploads.create_link("song.wav", replace=True)["upload_url"].rsplit("/", 1)[-1]
        result = uploads.receive(token, wav_bytes(523))
        self.assertEqual(result["status"], "modified")
        self.assertIn("ai modified", result["tags"])


class SelectionTests(VibiaServiceTestCase):
    def setUp(self):
        super().setUp()
        self.visible.ingest("one.wav", wav_payload(440))
        self.visible.ingest("two.wav", wav_payload(523))

    def test_selection_deduplicates_in_requested_order(self):
        paths = self.visible.select_paths(["two.wav", "one.wav", "two.wav"])
        self.assertEqual([path.name for path in paths], ["two.wav", "one.wav"])

    def test_selection_rejects_hidden_oversized_and_non_string_batches(self):
        limit = self.config.max_fetch_tracks
        with self.assertRaisesRegex(ValueError, str(limit)):
            self.visible.select_paths([f"track-{index}.wav" for index in range(limit + 1)])
        with self.assertRaisesRegex(ValueError, "must be a string"):
            self.visible.select_paths([["one.wav"]])
        self.hidden.set_hidden(["one.wav"], True)
        with self.assertRaises(PermissionError):
            self.visible.select_paths(["one.wav"])


if __name__ == "__main__":
    unittest.main()
