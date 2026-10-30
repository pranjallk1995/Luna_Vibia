"""Tests for the MCP tool surface, HTTP routes, and track delivery helpers."""

import asyncio
import base64
import json
import os
import tempfile
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from fakes import (
    FakeCaptioner,
    FakeEncoder,
    FakePublicURLRepository,
    FakeSpeakerPlayer,
    FakeTrackRepository,
    FakeVisia,
    wav_bytes,
    wav_payload,
)

from app.transport.branding import ServerBranding
from app.core.config import AppConfig
from app.services.downloads import DownloadStore
from app.transport.http_routes import VibiaHTTPRoutes
from app.transport.mcp_tools import VibiaMCPTools
from app.services.media import TrackArchive, display_name
from app.integrations.remote import TrackSourceResolver
from app.integrations.speakers import Speaker, SpeakerPlayer, WindowsSpeakerHelper
from app.services.application import VibiaService


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height from a PNG's IHDR header (the image has no Pillow)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


# Distinct fixtures: each colour name (from the image-era tests) is a different pitch.
PITCHES = {"red": 440, "blue": 523, "green": 587, "teal": 659, "purple": 698, "orange": 784, "navy": 880}


def wav_bytes_color(_format="WAV", color="red"):
    return wav_bytes(PITCHES.get(color, 440))


def wav_payload_color(color="red", size=None):
    pitch = PITCHES.get(color, 440) + (size[0] if size else 0)
    return wav_payload(pitch)


class ServerTestCase(unittest.TestCase):
    """Register the real adapters over an in-memory service graph."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.downloads_temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = AppConfig(
            track_dir=self.root,
            database_url="postgresql://test",
            ollama_url="http://ollama:11434",
            caption_model="test-caption",
            public_base_url="https://vault.example.test/vault",
            download_dir=Path(self.downloads_temp.name),
        )
        self.repository = FakeTrackRepository()
        self.service = VibiaService.create(
            self.config,
            self.repository,
            FakePublicURLRepository(self.repository),
            FakeCaptioner(),
            FakeEncoder(),
            FakeVisia(),
        )
        self.branding = ServerBranding()
        # Match production: a non-localhost bind leaves DNS-rebinding checks off for TestClient.
        self.server = FastMCP("Luna Vibia test", host="0.0.0.0", icons=self.branding.mcp_icons())
        self.mcp_tools = VibiaMCPTools(
            self.server,
            self.service,
            TrackSourceResolver(
                self.service.visible.decoder,
                self.config.max_track_bytes,
                self.config.max_upload_redirects,
            ),
        )
        VibiaHTTPRoutes(self.server, self.service, self.branding, "x" * 32)
        # Pitches no colour fixture uses, so test uploads are never duplicates of these.
        self.service.visible.ingest("one.wav", wav_payload(300))
        self.service.visible.ingest("two.wav", wav_payload(350))

    def tearDown(self) -> None:
        self.temp.cleanup()
        self.downloads_temp.cleanup()

    def resolver(self) -> TrackSourceResolver:
        return TrackSourceResolver(self.service.visible.decoder, 1024 * 1024, 3)

    def call(self, tool_name: str, arguments: dict):
        tool = self.server._tool_manager.get_tool(tool_name)
        return asyncio.run(tool.run(arguments))

    def client(self) -> TestClient:
        return TestClient(self.server.streamable_http_app())


class MCPToolTests(ServerTestCase):
    def test_upload_track_accepts_base64(self) -> None:
        result = self.call("upload_track", {"name": "chat.wav", "content_base64": wav_payload_color()})
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["name"], "chat.wav")
        self.assertTrue((self.root / "chat.wav").is_file())

    def test_upload_track_accepts_track_data_url(self) -> None:
        result = self.call(
            "upload_track",
            {"name": "chat.wav", "track_url": f"data:audio/wav;base64,{wav_payload_color()}"},
        )
        self.assertEqual(result["status"], "created")

    def test_upload_source_requires_exactly_one_input(self) -> None:
        resolver = self.resolver()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            resolver.resolve(None, None)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            resolver.resolve("aW1hZ2U=", "data:image/png;base64,aW1hZ2U=")

    def test_upload_source_rejects_private_network_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, "public"):
            self.resolver().resolve(None, "https://127.0.0.1/cat.wav")

    def test_get_track_url_returns_visible_https_location(self) -> None:
        self.assertEqual(
            self.call("get_track_url", {"name": "one.wav"}),
            {
                "name": "one.wav",
                "url": "https://vault.example.test/vault/api/public/tracks/track-1",
            },
        )

    def test_get_track_metadata_returns_stored_and_embedded_fields(self) -> None:
        metadata = self.call("get_track_metadata", {"name": "one.wav"})
        self.assertEqual(metadata["name"], "one.wav")
        self.assertEqual(metadata["tags"], ["piano", "calm"])
        self.assertEqual((metadata["file"]["format"], metadata["file"]["sample_rate"]), ("WAV", 48000))
        self.assertFalse(metadata["ai_generated"])

    def test_get_track_metadata_rejects_hidden_tracks(self) -> None:
        self.repository.rows["one.wav"]["hidden"] = True
        with self.assertRaises(ToolError):
            self.call("get_track_metadata", {"name": "one.wav"})

    def test_list_track_metadata_pages_compact_summaries(self) -> None:
        first = self.call("list_track_metadata", {"limit": 1})
        self.assertEqual((first["count"], first["next_offset"]), (2, 1))
        [item] = first["tracks"]
        self.assertEqual(item["embedded"]["format"], "WAV")
        self.assertFalse(item["embedded"]["ai_generated"])
        self.assertNotIn("embedded_tags", item)
        second = self.call("list_track_metadata", {"limit": 1, "offset": 1})
        self.assertIsNone(second["next_offset"])

    def test_list_track_metadata_batch_reports_unavailable_names(self) -> None:
        self.repository.rows["two.wav"]["hidden"] = True
        result = self.call(
            "list_track_metadata", {"names": ["one.wav", "two.wav", "missing.wav"], "detail": "full"}
        )
        self.assertEqual([item["name"] for item in result["tracks"]], ["one.wav"])
        self.assertIn("embedded_tags", result["tracks"][0])
        self.assertEqual(result["unavailable"], ["two.wav", "missing.wav"])

    def test_list_track_metadata_caps_full_detail_batches(self) -> None:
        with self.assertRaises(ToolError):
            self.call("list_track_metadata", {"names": [f"{i}.wav" for i in range(21)], "detail": "full"})

    def test_update_tracks_metadata_applies_each_change_and_reports_failures(self) -> None:
        result = self.call(
            "update_tracks_metadata",
            {
                "updates": [
                    {"name": "one.wav", "add_tags": ["food"], "remove_tags": ["calm"]},
                    {"name": "two.wav", "caption": "A blue square."},
                    {"name": "missing.wav", "add_tags": ["food"]},
                ]
            },
        )
        self.assertEqual((result["updated_count"], result["failed_count"]), (2, 1))
        self.assertEqual(self.repository.rows["one.wav"]["tags"], ["piano", "food"])
        self.assertEqual(self.repository.rows["two.wav"]["caption"], "A blue square.")
        self.assertEqual(result["failed"][0]["name"], "missing.wav")

    def test_update_tracks_metadata_rejects_capitalized_tags_without_changes(self) -> None:
        with self.assertRaises(ToolError):
            self.call(
                "update_tracks_metadata",
                {"updates": [{"name": "one.wav", "add_tags": ["food"]}, {"name": "two.wav", "add_tags": ["Food"]}]},
            )
        self.assertEqual(self.repository.rows["one.wav"]["tags"], ["piano", "calm"])

    def test_batch_update_reports_ai_info_removal_as_failure(self) -> None:
        from fakes import encoded

        self.service.visible.upload("generated.mp3", encoded("mp3", comment="Made with Suno"))
        result = self.call(
            "update_tracks_metadata",
            {
                "updates": [
                    {"name": "generated.mp3", "remove_tags": ["ai info"]},
                    {"name": "one.wav", "add_tags": ["food"]},
                ]
            },
        )
        self.assertEqual(result["updated_count"], 1)
        self.assertIn("cannot be removed", result["failed"][0]["error"])

    def test_batch_tool_schemas_are_inline(self) -> None:
        for name in ("update_tracks_metadata", "rename_tracks"):
            schema = json.dumps(self.server._tool_manager.get_tool(name).parameters)
            self.assertNotIn("$ref", schema)

    def test_rename_tracks_applies_in_order(self) -> None:
        result = self.call(
            "rename_tracks",
            {
                "renames": [
                    {"name": "one.wav", "new_name": "first.wav"},
                    {"name": "two.wav", "new_name": "one.wav"},
                    {"name": "first.wav", "new_name": "bad name.wav"},
                ]
            },
        )
        self.assertEqual([item["name"] for item in result["renamed"]], ["first.wav", "one.wav"])
        self.assertTrue(result["renamed"][0]["public_url"].endswith("/track-1"))
        self.assertEqual(result["failed"][0]["name"], "first.wav")
        self.assertTrue((self.root / "first.wav").is_file())

    def test_batch_updates_are_capped(self) -> None:
        with self.assertRaises(ToolError):
            self.call("rename_tracks", {"renames": [{"name": f"{i}.wav", "new_name": f"n{i}.wav"} for i in range(101)]})
        with self.assertRaises(ToolError):
            self.call("update_tracks_metadata", {"updates": []})

    def test_rename_track_preserves_public_url(self) -> None:
        renamed = self.call("rename_track", {"name": "one.wav", "new_name": "renamed.wav"})
        self.assertEqual(renamed["name"], "renamed.wav")
        self.assertTrue(renamed["public_url"].endswith("/track-1"))

    def test_set_public_base_url_updates_urls_from_chat(self) -> None:
        result = self.call(
            "set_public_base_url", {"public_base_url": "https://new.example.test/vault/"}
        )
        self.assertEqual(result["public_base_url"], "https://new.example.test/vault")
        self.assertEqual(result["updated_track_count"], 2)

    def test_set_favorite_tracks_adds_and_removes_from_chat(self) -> None:
        added = self.call("set_favorite_tracks", {"names": ["one.wav", "two.wav"], "favorite": True})
        removed = self.call("set_favorite_tracks", {"names": ["one.wav"], "favorite": False})
        self.assertEqual((added["status"], added["count"]), ("favorited", 2))
        self.assertEqual((removed["status"], removed["names"]), ("unfavorited", ["one.wav"]))

    def test_get_gallery_stats_counts_visible_tracks(self) -> None:
        self.call("set_favorite_tracks", {"names": ["one.wav"], "favorite": True})
        self.service.hidden.set_hidden(["two.wav"], True)
        stats = self.call("get_library_stats", {})
        self.assertEqual((stats["total_tracks"], stats["favorite_count"]), (1, 1))
        self.assertEqual(stats["largest_track"]["name"], "one.wav")

    def test_fetch_tracks_rejects_hidden_tracks(self) -> None:
        self.service.hidden.set_hidden(["one.wav"], True)
        with self.assertRaises(Exception):
            self.call("download_tracks", {"names": ["one.wav"]})

    def test_list_tracks_pages_compact_summaries(self) -> None:
        for index in range(3):
            self.service.visible.ingest(f"extra_{index}.wav", wav_payload_color("red", (5 + index, 3)))
        first = self.call("list_tracks", {"limit": 2})
        self.assertEqual((first["count"], first["offset"], first["next_offset"]), (5, 0, 2))
        self.assertEqual(
            set(first["tracks"][0]),
            {"name", "caption", "tags", "favorite", "title", "artist", "duration_seconds", "tempo_bpm",
             "musical_key", "energy", "cover_url", "updated_at", "public_url"},
        )
        last = self.call("list_tracks", {"limit": 2, "offset": 4})
        self.assertEqual((len(last["tracks"]), last["next_offset"]), (1, None))

    def test_search_and_playlist_return_playable_links(self) -> None:
        results = self.call("search_tracks", {"query": "calm piano"})
        self.assertTrue(all(item["public_url"] and "score" in item for item in results["results"]))
        self.assertIsNone(results["next_offset"])
        playlist = self.call("suggest_playlist", {"description": "calm piano", "minutes": 1})
        self.assertTrue(playlist["loop"])
        self.assertTrue(all(item["public_url"] for item in playlist["tracks"]))

    def test_set_track_cover_checks_luna_visia(self) -> None:
        from fakes import FakeVisia

        url = f"https://visia.example.test/api/public/images/{FakeVisia.VISIBLE_ID}"
        self.assertEqual(self.call("set_track_cover", {"name": "one.wav", "cover_url": url})["cover_url"], url)
        with self.assertRaises(ToolError):
            self.call("set_track_cover", {"name": "one.wav", "cover_url": "https://x.test/cat.png"})

    def test_fetch_tracks_zip_returns_download_link_not_blob(self) -> None:
        result = self.call("download_tracks", {"names": ["one.wav", "two.wav"], "delivery": "zip"})
        self.assertEqual(result["status"], "zip_ready")
        self.assertTrue(
            result["download_url"].startswith(
                "https://vault.example.test/vault/api/downloads/"
            )
        )
        self.assertEqual((result["track_count"], result["names"]), (2, ["one.wav", "two.wav"]))
        self.assertLess(len(json.dumps(result)), 1024)

    def test_fetch_tracks_zip_rejects_hidden_tracks(self) -> None:
        self.service.hidden.set_hidden(["one.wav"], True)
        with self.assertRaises(Exception):
            self.call("download_tracks", {"names": ["one.wav"], "delivery": "zip"})


class PlaceholderCoverToolTests(ServerTestCase):
    def test_cover_without_url_uses_the_audio_placeholder(self) -> None:
        from fakes import FakeVisia

        self.service.visible.covers = FakeVisia(FakeVisia.VISIBLE_ID)
        result = self.call("set_track_cover", {"name": "one.wav"})
        self.assertEqual(result["cover_url"], f"https://visia.example.test/api/public/images/{FakeVisia.VISIBLE_ID}")

    def test_cover_without_url_clears_while_no_placeholder_is_set(self) -> None:
        self.assertIsNone(self.call("set_track_cover", {"name": "one.wav"})["cover_url"])

    def test_missing_placeholder_is_reported(self) -> None:
        from fakes import FakeVisia

        self.service.visible.covers = FakeVisia(FakeVisia.HIDDEN_ID)
        with self.assertRaisesRegex(ToolError, "LUNAVIBIA_PLACEHOLDER_COVER_ID"):
            self.call("set_track_cover", {"name": "one.wav"})

    def test_upload_stores_the_checked_visia_cover(self) -> None:
        from fakes import FakeVisia

        url = f"https://anything.test/api/public/images/{FakeVisia.VISIBLE_ID}"
        result = self.call("upload_track", {"name": "chat.wav", "content_base64": wav_payload_color(), "cover_url": url})
        expected = f"https://visia.example.test/api/public/images/{FakeVisia.VISIBLE_ID}"
        self.assertEqual(result["cover_url"], expected)
        self.assertEqual(self.repository.rows["chat.wav"]["cover_url"], expected)

    def test_upload_without_cover_gets_the_audio_placeholder(self) -> None:
        from fakes import FakeVisia

        self.service.visible.covers = FakeVisia(FakeVisia.VISIBLE_ID)
        result = self.call("upload_track", {"name": "chat.wav", "content_base64": wav_payload_color()})
        self.assertEqual(result["cover_url"], f"https://visia.example.test/api/public/images/{FakeVisia.VISIBLE_ID}")

    def test_upload_with_unknown_cover_is_rejected_before_storing(self) -> None:
        from fakes import FakeVisia

        url = f"https://visia.example.test/api/public/images/{FakeVisia.HIDDEN_ID}"
        with self.assertRaises(ToolError):
            self.call("upload_track", {"name": "chat.wav", "content_base64": wav_payload_color(), "cover_url": url})
        self.assertFalse((self.root / "chat.wav").exists())

    def test_ui_clearing_a_cover_ignores_the_placeholder(self) -> None:
        from fakes import FakeVisia

        self.service.visible.covers = FakeVisia(FakeVisia.VISIBLE_ID)
        self.assertIsNone(self.service.visible.set_cover("one.wav", None)["cover_url"])


class LowercaseTagToolTests(ServerTestCase):
    """MCP tools reject capitalized tags instead of silently lowercasing them."""

    def tags_of(self, name: str) -> list[str]:
        return self.repository.get(name)["tags"]

    def test_capitalized_add_tags_are_rejected_without_changes(self) -> None:
        before = self.tags_of("one.wav")

        with self.assertRaisesRegex(ToolError, "add_tags must be lowercase.*'dinner'"):
            self.call("update_track_metadata", {"name": "one.wav", "add_tags": ["food", "Dinner"]})

        self.assertEqual(self.tags_of("one.wav"), before)

    def test_capitalized_remove_tags_are_rejected(self) -> None:
        with self.assertRaisesRegex(ToolError, "remove_tags must be lowercase"):
            self.call("update_track_metadata", {"name": "one.wav", "remove_tags": ["CAT"]})

    def test_capitalized_search_tags_are_rejected(self) -> None:
        with self.assertRaisesRegex(ToolError, "tags must be lowercase"):
            self.call("search_tracks", {"tags": ["Cat"]})

    def test_lowercase_tags_are_accepted(self) -> None:
        result = self.call("update_track_metadata", {"name": "one.wav", "add_tags": ["dinner"]})

        self.assertIn("dinner", result["tags"])
        self.assertIsInstance(self.call("search_tracks", {"tags": ["dinner"]}), dict)


class ChatUploadToolTests(ServerTestCase):
    def test_upload_tool_declares_chatgpt_file_param(self) -> None:
        tool = next(t for t in asyncio.run(self.server.list_tools()) if t.name == "upload_track")
        self.assertEqual(tool.meta, {"openai/fileParams": ["file"]})
        self.assertIn("download_url", json.dumps(tool.inputSchema["properties"]["file"]))
        self.assertNotIn("name", tool.inputSchema.get("required", []))

    def test_upload_from_chatgpt_file_reference(self) -> None:
        resolver = self.server_resolver()
        resolver._download = lambda url: (wav_bytes_color("JPEG"), url)
        result = self.call(
            "upload_track",
            {"file": {"download_url": "https://files.example.test/abc", "file_id": "file-1", "file_name": "Holiday.wav"}},
        )
        self.assertEqual((result["status"], result["name"]), ("created", "Holiday.wav"))

    def test_upload_without_name_uses_url_filename(self) -> None:
        self.server_resolver()._download = lambda url: (wav_bytes_color("PNG", "green"), url)
        result = self.call("upload_track", {"track_url": "https://cdn.example.test/photos/beach.wav"})
        self.assertEqual(result["name"], "beach.wav")

    def test_local_file_paths_explain_upload_link(self) -> None:
        for path in ("/mnt/data/cat.wav", "file:///tmp/cat.wav", "sandbox:/mnt/data/cat.wav"):
            with self.subTest(path), self.assertRaisesRegex(Exception, "create_upload_link"):
                self.call("upload_track", {"track_url": path})

    def test_slow_upload_does_not_block_event_loop(self) -> None:
        indexer = self.service.indexer
        original = indexer.analyze

        def slow(*args, **kwargs):
            time.sleep(0.5)
            return original(*args, **kwargs)

        indexer.analyze = slow

        async def scenario():
            upload = asyncio.create_task(
                self.server.call_tool("upload_track", {"name": "slow.wav", "content_base64": wav_payload_color("teal")})
            )
            started = time.monotonic()
            await asyncio.sleep(0.05)
            responsive_after = time.monotonic() - started
            await upload
            return responsive_after

        self.assertLess(asyncio.run(scenario()), 0.3)

    def server_resolver(self) -> TrackSourceResolver:
        return self.mcp_tools.sources


class UploadLinkRouteTests(ServerTestCase):
    def link_path(self, name: str = "cat.wav") -> str:
        url = self.call("create_upload_link", {"name": name})["upload_url"]
        return url.removeprefix("https://vault.example.test/vault")

    def test_raw_body_upload(self) -> None:
        path = self.link_path("cat")
        with self.client() as client:
            response = client.post(path, content=wav_bytes_color("PNG", "purple"))
            reused = client.post(path, content=wav_bytes_color("PNG", "orange"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "cat.wav")
        self.assertEqual(reused.status_code, 404)

    def test_multipart_upload(self) -> None:
        with self.client() as client:
            response = client.post(
                self.link_path("dog.wav"),
                files={"file": ("Recording 01.wav", wav_bytes_color("WAV", "navy"), "audio/wav")},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "dog.wav")

    def test_oversized_upload_is_rejected(self) -> None:
        self.service.uploads.max_bytes = 100
        with self.client() as client:
            response = client.post(self.link_path(), content=b"x" * 101)
        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.json()["error"])


class MediaTests(ServerTestCase):
    def test_display_name_drops_upload_prefix(self) -> None:
        self.assertEqual(display_name(f"{'a' * 32}_Big_Ben.wav"), "Big_Ben.wav")
        self.assertEqual(display_name("plain.wav"), "plain.wav")

    def test_archive_stores_originals_uncompressed(self) -> None:
        destination = Path(self.downloads_temp.name) / "test.zip"
        TrackArchive.write([self.root / "two.wav"], destination)
        with zipfile.ZipFile(destination) as bundle:
            entry = bundle.getinfo("two.wav")
            self.assertEqual(entry.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(bundle.read("two.wav"), (self.root / "two.wav").read_bytes())

    def test_archive_entry_names_drop_upload_prefix_and_stay_unique(self) -> None:
        prefix_a, prefix_b = "a" * 32, "b" * 32
        names = TrackArchive.entry_names(
            [Path(f"{prefix_a}_cat.wav"), Path(f"{prefix_b}_cat.wav"), Path("Cat.wav"), Path("dog.wav")]
        )
        self.assertEqual(names, ["cat.wav", "cat (2).wav", "Cat (3).wav", "dog.wav"])


class DownloadRouteTests(ServerTestCase):
    def create_zip(self, names: list[str]) -> dict:
        return self.call("download_tracks", {"names": names, "delivery": "zip"})

    @staticmethod
    def path_of(download_url: str) -> str:
        return download_url.removeprefix("https://vault.example.test/vault")

    def test_download_link_serves_zip_attachment(self) -> None:
        result = self.create_zip(["two.wav", "one.wav"])
        with self.client() as client:
            response = client.get(self.path_of(result["download_url"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn("luna-vibia-tracks.zip", response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(response.content), result["size_bytes"])
        with zipfile.ZipFile(BytesIO(response.content)) as bundle:
            self.assertEqual(bundle.namelist(), ["two.wav", "one.wav"])
            self.assertEqual(bundle.read("one.wav"), (self.root / "one.wav").read_bytes())

    def test_zip_exceeding_display_limits_is_allowed(self) -> None:
        names = []
        for index in range(self.config.max_fetch_tracks + 5):
            name = f"bulk_{index}.wav"
            self.service.visible.ingest(name, wav_payload_color("red"))
            names.append(name)
        result = self.create_zip(names)
        self.assertEqual(result["track_count"], len(names))

    def test_zip_enforces_archive_limits(self) -> None:
        downloads = self.service.downloads
        downloads.max_bytes = 10
        with self.assertRaisesRegex(ValueError, "limit"):
            downloads.create_zip(["one.wav"])

    def test_unknown_or_expired_links_return_404_and_are_purged(self) -> None:
        live = self.create_zip(["one.wav"])
        self.service.downloads.store.ttl_seconds = 0
        expired = self.create_zip(["two.wav"])
        with self.client() as client:
            self.assertEqual(client.get("/api/downloads/not-a-token").status_code, 404)
            self.assertEqual(client.get(self.path_of(expired["download_url"])).status_code, 404)
            self.assertEqual(client.get(self.path_of(live["download_url"])).status_code, 200)
        remaining = [path.stem for path in Path(self.downloads_temp.name).glob("*.zip")]
        self.assertEqual(remaining, [live["download_url"].rsplit("/", 1)[-1]])

    def store_dir(self) -> Path:
        return Path(self.downloads_temp.name)

    def test_link_survives_restart(self) -> None:
        result = self.create_zip(["one.wav", "two.wav"])
        # A new store over the same directory models a service restart.
        self.service.downloads.store = DownloadStore(self.store_dir(), 3600, 10**9)
        with self.client() as client:
            response = client.get(self.path_of(result["download_url"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.content), result["size_bytes"])

    def test_store_evicts_oldest_archives_over_size_cap(self) -> None:
        first = self.create_zip(["one.wav"])
        size = first["size_bytes"]
        self.service.downloads.store.max_total_bytes = size + 1
        second = self.create_zip(["two.wav"])
        with self.client() as client:
            self.assertEqual(client.get(self.path_of(first["download_url"])).status_code, 404)
            self.assertEqual(client.get(self.path_of(second["download_url"])).status_code, 200)

    def test_incomplete_archive_without_ticket_is_not_served(self) -> None:
        token = "A" * 43
        (self.store_dir() / f"{token}.zip").write_bytes(b"partial")
        with self.client() as client:
            self.assertEqual(client.get(f"/api/downloads/{token}").status_code, 404)

    def test_malformed_tokens_cannot_reach_other_files(self) -> None:
        with self.client() as client:
            for token in ("..%2F..%2Fetc%2Fpasswd", "short", "A" * 42 + "."):
                self.assertEqual(client.get(f"/api/downloads/{token}").status_code, 404)

    def test_abandoned_leftovers_are_purged_after_grace(self) -> None:
        store = self.service.downloads.store
        leftover = self.store_dir() / f"{'B' * 43}.zip"
        leftover.write_bytes(b"orphan")
        store.purge()
        self.assertTrue(leftover.exists())
        old = time.time() - AppConfig.DOWNLOAD_LEFTOVER_GRACE_SECONDS - 1
        os.utime(leftover, (old, old))
        store.purge()
        self.assertFalse(leftover.exists())


class PlaybackToolTests(ServerTestCase):
    LOUNGE = Speaker("alsa_output.lounge", "Lounge Speaker", True)
    DESK = Speaker("bluez_output.desk", "Desk Headphones", False)

    def connect(self, *speakers: Speaker) -> FakeSpeakerPlayer:
        player = FakeSpeakerPlayer(list(speakers))
        self.service.playback.player = player
        return player

    def test_sink_list_is_parsed_with_default_marked(self) -> None:
        output = "Auto-detected sinks for pulse:\n* RDPSink [RDP Sink] (none)\n  usb.out [USB Audio [2]] (none)\n"
        self.assertEqual(
            SpeakerPlayer.parse_sinks(output),
            [Speaker("RDPSink", "RDP Sink", True), Speaker("usb.out", "USB Audio [2]", False)],
        )
        self.assertEqual(SpeakerPlayer.parse_sinks("Cannot list sinks: Generic error\n"), [])

    def test_single_speaker_plays_without_asking(self) -> None:
        player = self.connect(self.LOUNGE)
        result = self.call("play_tracks", {"names": ["one.wav", "two.wav", "one.wav"], "loop": True})
        self.assertEqual((result["status"], result["tracks"], result["loop"]), ("playing", ["one.wav", "two.wav"], True))
        queue, speaker, _ = player.played[0]
        self.assertEqual((speaker, queue[0]), (self.LOUNGE, ("one.wav", self.root / "one.wav")))

    def test_several_speakers_ask_which_one_when_unspecified(self) -> None:
        player = self.connect(self.LOUNGE, self.DESK)
        result = self.call("play_tracks", {"names": ["one.wav"]})
        self.assertEqual(result["status"], "choose_speaker")
        self.assertEqual([option["name"] for option in result["speakers"]], [self.LOUNGE.name, self.DESK.name])
        self.assertEqual(player.played, [])

    def test_speaker_is_matched_by_name_or_description(self) -> None:
        player = self.connect(self.LOUNGE, self.DESK)
        self.call("play_tracks", {"names": ["one.wav"], "speaker": "desk headphones"})
        self.call("play_tracks", {"names": ["one.wav"], "speaker": self.LOUNGE.name})
        self.assertEqual([speaker for _, speaker, _ in player.played], [self.DESK, self.LOUNGE])

    def test_unknown_or_ambiguous_speaker_lists_options(self) -> None:
        self.connect(self.LOUNGE, self.DESK)
        with self.assertRaisesRegex(ToolError, "matches no speaker.*Lounge Speaker"):
            self.call("play_tracks", {"names": ["one.wav"], "speaker": "kitchen"})
        with self.assertRaisesRegex(ToolError, "matches several speakers"):
            self.call("play_tracks", {"names": ["one.wav"], "speaker": "_output"})

    def test_hidden_tracks_cannot_be_played(self) -> None:
        player = self.connect(self.LOUNGE)
        self.service.hidden.set_hidden(["one.wav"], True)
        with self.assertRaises(ToolError):
            self.call("play_tracks", {"names": ["one.wav"]})
        self.assertEqual(player.played, [])

    def test_windows_speakers_switch_the_default_then_play_on_it(self) -> None:
        echo = Speaker("Echo Dot-PL7", "Speakers (Echo Dot-PL7)", False, "{0.0.0.00000000}.{f957}")

        class FakeWindows:
            selected: list[Speaker] = []

            def speakers(self):
                return [echo]

            def select(self, speaker):
                self.selected.append(speaker)

        windows = FakeWindows()
        player = SpeakerPlayer(windows)
        commands = []
        player._run = lambda queue, sink, loop, stop, *start: commands.append(player._command(queue[0][1], sink, queue[0][0]))
        self.service.playback.player = player
        result = self.call("play_tracks", {"names": ["one.wav"], "speaker": "echo dot"})
        self.assertEqual((result["status"], result["speaker"]["name"]), ("playing", "Echo Dot-PL7"))
        self.assertEqual(windows.selected, [echo])
        self.assertNotIn("-device", commands[0])

    def test_list_speakers_and_status(self) -> None:
        self.connect(self.LOUNGE, self.DESK)
        speakers = self.call("list_speakers", {})
        self.assertEqual((speakers["count"], speakers["speakers"][0]["default"]), (2, True))
        self.assertEqual(self.call("get_playback_status", {}), {"status": "idle", "output": self.LOUNGE.as_row()})
        self.call("play_tracks", {"names": ["two.wav"], "speaker": "desk"})
        playing = self.call("get_playback_status", {})
        self.assertEqual((playing["now_playing"], playing["output"]), ("two.wav", self.DESK.as_row()))
        self.assertNotIn("requested_speaker", playing)
        self.assertEqual(playing["track"]["name"], "two.wav")
        self.assertIn("tags", playing["track"])
        with self.client() as client:
            light = client.get("/api/playback", params={"output": "0"}).json()
        self.assertEqual(light["track"]["name"], "two.wav")
        self.assertNotIn("output", light)
        self.assertEqual(self.call("stop_playback", {}), {"status": "stopped"})
        self.assertEqual(self.call("get_playback_status", {})["status"], "idle")

    def test_status_reports_the_speaker_windows_switched_to(self) -> None:
        echo = Speaker("Echo Dot-PL7", "Speakers (Echo Dot-PL7)", True, "echo-id")
        spinx = {"name": "Stone Spinx Pro", "description": "Bluetooth Speakers (Stone Spinx Pro)", "bluetooth": True}

        class FakeWindows:
            output = {"name": echo.name, "description": echo.description, "bluetooth": True}

            def speakers(self):
                return [echo]

            def current(self):
                return self.output

        windows = FakeWindows()
        player = SpeakerPlayer(windows)
        player._run = lambda queue, sink, loop, stop, *start: None
        self.service.playback.player = player
        self.call("play_tracks", {"names": ["one.wav"]})
        self.assertNotIn("requested_speaker", self.call("get_playback_status", {}))
        windows.output = spinx
        status = self.call("get_playback_status", {})
        self.assertEqual((status["speaker"], status["output"]), (spinx, spinx))
        self.assertEqual(status["requested_speaker"]["name"], "Echo Dot-PL7")
        self.assertIn("Stone Spinx Pro", status["note"])
        with self.client() as client:
            self.assertEqual(client.get("/api/playback").json()["speaker"], spinx)


    def test_switching_speaker_resumes_the_track_where_it_was(self) -> None:
        lounge, desk = Speaker("lounge", "Lounge", True), Speaker("desk", "Desk", False)
        player = SpeakerPlayer()
        player.speakers = lambda: [lounge, desk]
        runs = []
        player._run = lambda queue, sink, loop, stop, *start: runs.append((sink, loop, *start))
        self.service.playback.player = player
        self.call("play_tracks", {"names": ["one.wav", "two.wav"], "speaker": "lounge", "loop": True})
        self.assertEqual(runs[-1], ("lounge", True, 0, 0.0))
        player._state["now_playing"] = "two.wav"
        player._track_started -= 42
        self.assertAlmostEqual(self.call("get_playback_status", {})["position_seconds"], 42, delta=1)
        moved = self.call("switch_speaker", {"speaker": "desk"})
        self.assertEqual((moved["speaker"]["name"], moved["now_playing"]), ("desk", "two.wav"))
        sink, loop, track, seconds = runs[-1]
        self.assertEqual((sink, loop, track), ("desk", True, 1))
        self.assertAlmostEqual(seconds, 42, delta=1)
        self.assertIn("-ss", player._command(Path("two.wav"), sink, "two.wav", seconds))
        # The same queue through play_tracks carries on too.
        self.call("play_tracks", {"names": ["one.wav", "two.wav"], "speaker": "lounge", "loop": True})
        self.assertEqual(runs[-1][2], 1)
        self.call("play_tracks", {"names": ["one.wav"], "speaker": "lounge"})
        self.assertEqual(runs[-1][2:], (0, 0.0))
        player.stop()
        with self.assertRaises(ToolError):
            self.call("switch_speaker", {"speaker": "desk"})

    def test_beat_map_is_worked_out_once_and_status_says_when_the_track_started(self) -> None:
        with self.client() as client:
            first = client.get("/api/tracks/one.wav/beats").json()
        self.assertEqual(first["name"], "one.wav")
        self.assertEqual(len(first["beats"]), len(first["strengths"]))
        self.assertEqual(len(self.repository.beat_maps), 1)
        with patch("app.integrations.audio.MusicFeatures.beat_map", side_effect=AssertionError("recomputed")):
            self.assertEqual(self.service.playback.beats("one.wav")["beats"], first["beats"])
        self.connect(self.LOUNGE)
        self.call("play_tracks", {"names": ["one.wav"]})
        player = self.service.playback.player
        player._track_started = time.monotonic() - 30
        status = self.call("get_playback_status", {})
        self.assertAlmostEqual(time.time() - status["started_at"], 30, delta=1)

    def test_volume_tools_turn_the_current_speaker_up_down_and_mute_it(self) -> None:
        class FakeWindows:
            state = {"volume": 40, "muted": False, "name": "Echo Dot-PL7", "description": "Speakers (Echo Dot-PL7)"}

            def volume(self):
                return dict(self.state)

            def set_volume(self, percent=None, change=None, muted=None):
                if change is not None:
                    percent = self.state["volume"] + change
                if percent is not None:
                    self.state["volume"] = max(0, min(100, percent))
                if muted is not None:
                    self.state["muted"] = muted
                return dict(self.state)

        self.service.playback.player = SpeakerPlayer(FakeWindows())
        self.assertEqual(self.call("get_volume", {})["volume"], 40)
        self.assertEqual(self.call("change_volume", {"by": 10})["volume"], 50)
        self.assertEqual(self.call("change_volume", {"by": -25})["volume"], 25)
        quiet = self.call("set_volume", {"percent": 5, "muted": True})
        self.assertEqual((quiet["volume"], quiet["muted"]), (5, True))
        with self.assertRaisesRegex(ToolError, "percent, muted"):
            self.call("set_volume", {})
        self.service.playback.player = SpeakerPlayer()
        with self.assertRaisesRegex(ToolError, "Windows speaker helper"):
            self.call("get_volume", {})

    def test_windows_helper_sends_volume_changes(self) -> None:
        helper = WindowsSpeakerHelper("http://helper", "token")

        class Response:
            is_error = False

            def json(self):
                return {"volume": 30, "muted": False}

        with patch("httpx.request", return_value=Response()) as request:
            helper.set_volume(change=-10)
        method, url = request.call_args.args
        self.assertEqual((method, url, request.call_args.kwargs["json"]), ("POST", "http://helper/speakers/volume", {"change": -10}))

    def test_windows_helper_reads_the_current_output_quickly(self) -> None:
        helper = WindowsSpeakerHelper("http://helper", "token")
        output = {"id": "x", "name": "Echo Dot-PL7", "description": "Speakers (Echo Dot-PL7)", "bluetooth": True}

        class Response:
            is_error = False

            def json(self):
                return output

        with patch("httpx.request", return_value=Response()) as request:
            self.assertEqual(helper.current()["name"], "Echo Dot-PL7")
        self.assertEqual(request.call_args.kwargs["timeout"], AppConfig.SPEAKER_OUTPUT_TIMEOUT_SECONDS)
        output["id"] = ""
        with patch("httpx.request", return_value=Response()):
            self.assertIsNone(helper.current())

class HTTPRouteTests(ServerTestCase):
    def test_health_route_reports_service_status(self) -> None:
        with self.client() as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "luna-vibia"})

    def test_metadata_route_lists_visible_tracks(self) -> None:
        self.service.hidden.set_hidden(["two.wav"], True)
        with self.client() as client:
            tracks = client.get("/api/metadata").json()["tracks"]
        self.assertEqual([track["name"] for track in tracks], ["one.wav"])

    def test_public_track_route_serves_by_stable_id(self) -> None:
        with self.client() as client:
            response = client.get("/api/public/tracks/track-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, (self.root / "one.wav").read_bytes())
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_upload_route_returns_created_metadata(self) -> None:
        with self.client() as client:
            response = client.post(
                "/api/tracks", json={"name": "new.wav", "content_base64": wav_payload_color()}
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "created")

    def test_favorites_route_requires_boolean(self) -> None:
        with self.client() as client:
            response = client.post("/api/favorites", json={"names": ["one.wav"], "favorite": "yes"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("favorite", response.json()["error"])

    def test_hidden_routes_are_available_to_the_oauth_gated_ui(self) -> None:
        headers = {"Authorization": f"Bearer {'x' * 32}"}
        with self.client() as client:
            self.assertEqual(client.get("/api/hidden/tracks").status_code, 401)
            hidden = client.post(
                "/api/hidden/hide", json={"names": ["one.wav"]}, headers=headers
            )
            tracks = client.get("/api/hidden/tracks", headers=headers).json()["tracks"]
            updated = client.post(
                "/api/hidden/tracks/one.wav/metadata",
                json={"add_tags": ["Private"]},
                headers=headers,
            )
        self.assertEqual(hidden.json()["status"], "hidden")
        self.assertEqual([track["name"] for track in tracks], ["one.wav"])
        self.assertEqual(updated.json()["tags"], ["piano", "calm", "private"])


class BrandingTests(ServerTestCase):
    def test_favicon_route_serves_icon(self) -> None:
        with self.client() as client:
            response = client.get("/favicon.ico")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/x-icon")
        self.assertEqual(response.content[:4], b"\x00\x00\x01\x00")  # the ICO header

    def test_icon_route_serves_bundled_png_sizes(self) -> None:
        with self.client() as client:
            for size in ServerBranding.ICON_SIZES:
                response = client.get(f"/icons/icon-{size}.png")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(png_size(response.content), (size, size))

    def test_icon_route_rejects_unknown_names(self) -> None:
        with self.client() as client:
            for name in ("icon-1.png", "favicon.ico", "..%2Fbranding.py"):
                self.assertNotEqual(client.get(f"/icons/{name}").status_code, 200)

    def test_home_page_links_the_icons(self) -> None:
        with self.client() as client:
            page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        self.assertIn('href="/icons/icon-192.png"', page.text)
        self.assertIn('href="/favicon.ico"', page.text)

    def test_public_url_icons_are_listed_before_embedded_ones(self) -> None:
        icons = ServerBranding("https://mcp.example.com/").mcp_icons()
        self.assertEqual(
            [icon.src for icon in icons[:4]],
            [f"https://mcp.example.com/icons/icon-{size}.png" for size in ServerBranding.ICON_SIZES],
        )
        self.assertTrue(icons[4].src.startswith("data:image/png;base64,"))

    def test_initialize_advertises_server_icons(self) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        with self.client() as client:
            response = client.post(
                "/mcp",
                json=request,
                headers={"Accept": "application/json, text/event-stream"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = next(
            line.removeprefix("data:").strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        )
        icons = json.loads(data)["result"]["serverInfo"]["icons"]
        self.assertEqual([icon["sizes"] for icon in icons], [["48x48"], ["96x96"]])
        for icon in icons:
            self.assertEqual(icon["mimeType"], "image/png")
            header, payload = icon["src"].split(",", 1)
            self.assertEqual(header, "data:image/png;base64")
            width, height = png_size(base64.b64decode(payload))
            self.assertEqual(f"{width}x{height}", icon["sizes"][0])


if __name__ == "__main__":
    unittest.main()
