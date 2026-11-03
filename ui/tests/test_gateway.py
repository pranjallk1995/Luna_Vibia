import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from starlette.testclient import TestClient

from config import SSOConfig, UIConfig
from gateway import UIGateway

OWNER = {"user_id": "owner", "email": "owner@example.com", "email_verified": True}
STRANGER = {"user_id": "stranger", "email": "other@example.com", "email_verified": True}
TOKEN = "t" * 32
COVER = "https://visia.example.com/api/public/images/12345678-1234-1234-1234-123456789012"


def png() -> bytes:
    data = BytesIO()
    Image.new("RGB", (64, 32), "red").save(data, "PNG")
    return data.getvalue()


class GatewayTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.track_dir = Path(directory.name) / "u_owner"
        self.track_dir.mkdir()
        (self.track_dir / "a.mp3").write_bytes(b"0123456789")
        (self.track_dir / "b b.wav").write_bytes(b"wav")
        self.backend_requests: list[httpx.Request] = []
        self.visia_requests: list[httpx.Request] = []
        self.visia_up = True

        def sso(request: httpx.Request) -> httpx.Response:
            session = {"owner": OWNER, "stranger": STRANGER}.get(request.headers["X-Luna-Session"])
            return httpx.Response(200, json=session) if session else httpx.Response(401)

        def backend(request: httpx.Request) -> httpx.Response:
            self.backend_requests.append(request)
            if request.url.path == "/api/metadata":
                tracks = [{"name": "a.mp3", "tags": ["x"]}, {"name": "b b.wav"}, {"name": "gone.mp3"}]
                return httpx.Response(200, json={"tracks": tracks})
            return httpx.Response(200, json={"status": "ok"})

        def visia(request: httpx.Request) -> httpx.Response:
            self.visia_requests.append(request)
            return httpx.Response(200, content=png()) if self.visia_up else httpx.Response(503)

        config = UIConfig(
            track_dir=self.track_dir.parent,
            api_url="http://backend",
            api_token=TOKEN,
            allowed_emails=frozenset({"owner@example.com"}),
            sso=SSOConfig(public_url="https://auth.example.com"),
        )
        gateway = UIGateway(config, httpx.MockTransport(backend), httpx.MockTransport(sso), httpx.MockTransport(visia))
        self.client = TestClient(gateway.application(), base_url="https://vibia.example.com")

    def sign_in(self, who: str = "owner") -> None:
        self.client.cookies.set(SSOConfig.COOKIE_NAME, who)


class AccessTests(GatewayTestCase):
    def test_every_data_route_needs_an_allowed_session(self):
        for path in ("/app/tracks", "/app/hidden", "/app/covers/a.mp3", "/app/files/a.mp3", "/api/playback"):
            self.client.cookies.clear()
            self.assertEqual(self.client.get(path).status_code, 401, path)
            self.sign_in("stranger")
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(self.backend_requests, [])

    def test_settings_reach_the_browser_but_never_the_token(self):
        self.sign_in()
        response = self.client.get("/auth/session")
        self.assertEqual(response.json()["settings"]["tracks_per_page"], UIConfig.TRACKS_PER_PAGE)
        self.assertNotIn(TOKEN, response.text)


class CollectionTests(GatewayTestCase):
    def test_lists_only_tracks_with_files_with_their_facts(self):
        self.sign_in()
        tracks = {track["name"]: track for track in self.client.get("/app/tracks").json()["tracks"]}
        self.assertEqual(set(tracks), {"a.mp3", "b b.wav"})
        self.assertEqual(tracks["a.mp3"]["size_bytes"], 10)
        self.assertIn("version", tracks["a.mp3"])
        self.assertEqual(self.backend_requests[0].headers["Authorization"], f"Bearer {TOKEN}")


class FileTests(GatewayTestCase):
    def test_serves_audio_with_its_type_and_seeking(self):
        self.sign_in()
        response = self.client.get("/app/files/a.mp3")
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        partial = self.client.get("/app/files/a.mp3", headers={"Range": "bytes=2-4"})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, b"234")

    def test_download_keeps_the_display_name(self):
        self.sign_in()
        response = self.client.get("/app/files/a.mp3?download=song.mp3")
        self.assertIn("song.mp3", response.headers["content-disposition"])

    def test_refuses_traversal_and_other_files(self):
        (self.track_dir / "secret.txt").write_text("x")
        self.sign_in()
        self.assertEqual(self.client.get("/app/files/secret.txt").status_code, 404)
        self.assertEqual(self.client.get("/app/files/..%2F..%2Fetc%2Fpasswd").status_code, 404)


class CoverTests(GatewayTestCase):
    def test_placeholder_without_a_cover_is_cached_for_good(self):
        self.sign_in()
        response = self.client.get("/app/covers/a.mp3?size=card")
        self.assertEqual(response.headers["content-type"], "image/webp")
        self.assertIn("immutable", response.headers["cache-control"])
        self.assertEqual(self.visia_requests, [])

    def test_visia_image_is_fetched_once_over_the_private_network(self):
        self.sign_in()
        for _ in range(2):
            response = self.client.get("/app/covers/a.mp3", params={"size": "large", "cover": COVER})
            self.assertEqual(response.status_code, 200)
            self.assertIn("immutable", response.headers["cache-control"])
        self.assertEqual(len(self.visia_requests), 1)
        self.assertEqual(self.visia_requests[0].url.host, "luna-visia-mcp")

    def test_visia_away_gives_a_placeholder_that_is_asked_for_again(self):
        self.sign_in()
        self.visia_up = False
        response = self.client.get("/app/covers/a.mp3", params={"cover": COVER})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], UIConfig.RETRY_CACHE_CONTROL)
        self.visia_up = True
        self.assertIn("immutable", self.client.get("/app/covers/a.mp3", params={"cover": COVER}).headers["cache-control"])

    def test_other_addresses_are_never_fetched(self):
        self.sign_in()
        self.client.get("/app/covers/a.mp3", params={"cover": "http://169.254.169.254/latest/meta-data"})
        self.assertEqual(self.visia_requests, [])

    def test_unknown_size_is_refused(self):
        self.sign_in()
        self.assertEqual(self.client.get("/app/covers/a.mp3?size=huge").status_code, 400)


class ProxyTests(GatewayTestCase):
    def test_changes_the_ui_makes_are_forwarded_with_names_encoded(self):
        self.sign_in()
        for method, path in (
            ("POST", "/api/tracks"),
            ("DELETE", "/api/tracks/b%20b.wav"),
            ("POST", "/api/tracks/a.mp3/rename"),
            ("POST", "/api/tracks/a.mp3/cover"),
            ("POST", "/api/favorites"),
            ("POST", "/api/hidden/restore"),
            ("POST", "/api/hidden/tracks/a.mp3/metadata"),
        ):
            self.assertEqual(self.client.request(method, path).status_code, 200, path)
        self.assertEqual(self.backend_requests[1].url.raw_path, b"/api/tracks/b%20b.wav")

    def test_routes_the_ui_does_not_use_are_not_forwarded(self):
        self.sign_in()
        for method, path in (("GET", "/api/metadata"), ("POST", "/api/uploads/x"), ("GET", "/api/tracks/a.mp3/beats")):
            self.assertEqual(self.client.request(method, path).status_code, 404, path)
        self.assertEqual(self.backend_requests, [])


class ApplicationTests(GatewayTestCase):
    def test_health_needs_no_session_on_both_paths(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/_stcore/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
