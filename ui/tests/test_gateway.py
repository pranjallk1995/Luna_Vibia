import json
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
PIN = "246810"
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

        self.pin_set, self.sentia_up, self.hidden = True, True, set()
        self.sso_requests: list[httpx.Request] = []

        def sso(request: httpx.Request) -> httpx.Response:
            self.sso_requests.append(request)
            session = {"owner": OWNER, "owner-phone": OWNER, "stranger": STRANGER}.get(request.headers["X-Luna-Session"])
            if not session:
                return httpx.Response(401)
            if request.url.path == "/pin/status":
                return httpx.Response(200, json={"pin_set": self.pin_set, "locked_seconds": 0})
            if request.url.path == "/pin/verify":
                if not self.sentia_up:
                    return httpx.Response(503)
                if json.loads(request.content)["pin"] == PIN:
                    return httpx.Response(200, json={"ok": True})
                return httpx.Response(403, json={"error": "Wrong PIN. 4 tries left.", "attempts_left": 4})
            return httpx.Response(200, json=session)

        def backend(request: httpx.Request) -> httpx.Response:
            self.backend_requests.append(request)
            if request.url.path == "/api/hidden/tracks":
                return httpx.Response(200, json={"tracks": [{"name": name} for name in sorted(self.hidden)]})
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
        self.gateway = gateway = UIGateway(config, httpx.MockTransport(backend), httpx.MockTransport(sso), httpx.MockTransport(visia))
        self.client = TestClient(gateway.application(), base_url="https://vibia.example.com")

    def unlock(self, pin: str = None) -> httpx.Response:
        return self.client.post("/app/hidden/unlock", json={"pin": pin or PIN})

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
        self.unlock()
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

    def test_playlist_routes_are_forwarded_with_names_encoded(self):
        self.sign_in()
        for method, path in (
            ("GET", "/api/playlists"),
            ("POST", "/api/playlists"),
            ("GET", "/api/playlists/Late%20night"),
            ("POST", "/api/playlists/Late%20night"),
            ("DELETE", "/api/playlists/Late%20night"),
            ("POST", "/api/playlists/Late%20night/add"),
            ("POST", "/api/playlists/Late%20night/remove"),
            ("POST", "/api/playlists/Late%20night/order"),
            ("POST", "/api/playlists/Late%20night/move"),
        ):
            self.assertEqual(self.client.request(method, path).status_code, 200, path)
        self.assertEqual(self.backend_requests[-1].url.raw_path, b"/api/playlists/Late%20night/move")
        self.assertEqual(self.client.post("/api/playlists/Late%20night/play").status_code, 404)

    def test_routes_the_ui_does_not_use_are_not_forwarded(self):
        self.sign_in()
        for method, path in (("GET", "/api/metadata"), ("POST", "/api/uploads/x"), ("GET", "/api/tracks/a.mp3/beats")):
            self.assertEqual(self.client.request(method, path).status_code, 404, path)
        self.assertEqual(self.backend_requests, [])


class ApplicationTests(GatewayTestCase):
    def test_health_needs_no_session_on_both_paths(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/_stcore/health").status_code, 200)




class BulkProxyTests(GatewayTestCase):
    def test_bulk_routes_are_forwarded_with_a_batch_timeout(self):
        self.sign_in()
        self.unlock()
        for path in ("/api/tracks/delete", "/api/tracks/metadata", "/api/hidden/tracks/metadata", "/api/hidden/hide", "/api/favorites"):
            self.assertEqual(self.client.post(path, json={}).status_code, 200, path)
            self.assertEqual(self.backend_requests[-1].url.path, path)
            self.assertEqual(self.backend_requests[-1].extensions["timeout"]["read"], UIConfig.BATCH_TIMEOUT_SECONDS)

    def test_hidden_batch_edits_wait_for_the_pin(self):
        self.sign_in()
        self.assertEqual(self.client.post("/api/hidden/tracks/metadata", json={}).status_code, 423)

    def test_the_browser_learns_the_batch_size(self):
        self.sign_in()
        self.assertEqual(self.client.get("/auth/session").json()["settings"]["batch_size"], UIConfig.BATCH_SIZE)

class HiddenPinTests(GatewayTestCase):
    """Hidden tracks wait for the PIN that Luna Sentia checks."""

    FILE_ROUTES = (
            "/app/covers/{name}",
            "/app/files/{name}",
    )

    def expire_unlock(self):
        self.gateway.pin.unlocks = {key: (0.0, 0.0) for key in self.gateway.pin.unlocks}

    def test_the_hidden_tab_waits_for_the_right_pin(self):
        self.sign_in()
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)
        status = self.client.get("/app/hidden/pin").json()
        self.assertEqual((status["pin_set"], status["unlocked"]), (True, False))
        self.assertEqual(status["settings_url"], "https://auth.example.com/pin?next=https%3A%2F%2Fvibia.example.com%2F")
        wrong = self.unlock("111111")
        self.assertEqual((wrong.status_code, wrong.json()["attempts_left"]), (403, 4))
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)
        self.assertEqual(self.unlock().json(), {"unlocked": True})
        self.assertEqual(self.client.get("/app/hidden").status_code, 200)
        self.assertTrue(self.client.get("/app/hidden/pin").json()["unlocked"])

    def test_locking_again_and_going_idle_close_it(self):
        self.sign_in()
        self.unlock()
        self.client.post("/app/hidden/lock")
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)
        self.unlock()
        self.expire_unlock()
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)

    def test_the_pin_is_checked_by_sentia_with_this_session(self):
        self.sign_in()
        self.unlock()
        verify = [request for request in self.sso_requests if request.url.path == "/pin/verify"][-1]
        self.assertEqual(verify.headers["X-Luna-Session"], "owner")
        self.assertEqual(str(verify.url), "http://luna-sentia-auth:8000/pin/verify")

    def test_unlocking_lasts_only_for_this_session(self):
        self.sign_in()
        self.unlock()
        self.sign_in("owner-phone")
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)

    def test_without_a_pin_the_tab_asks_for_one_to_be_set(self):
        self.pin_set = False
        self.sign_in()
        status = self.client.get("/app/hidden/pin").json()
        self.assertEqual((status["pin_set"], status["unlocked"]), (False, False))
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)

    def test_sentia_being_away_is_reported_and_unlocks_nothing(self):
        self.sentia_up = False
        self.sign_in()
        self.assertEqual(self.unlock().status_code, 409)
        self.assertEqual(self.client.get("/app/hidden").status_code, 423)

    def test_hidden_files_wait_for_the_pin_and_are_never_cached(self):
        self.hidden = {"a.mp3"}
        self.sign_in()
        for route in self.FILE_ROUTES:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route.format(name="a.mp3")).status_code, 404)
                self.assertNotEqual(self.client.get(route.format(name="b b.wav")).status_code, 404)
        self.unlock()
        for route in self.FILE_ROUTES:
            with self.subTest(route=route, unlocked=True):
                answer = self.client.get(route.format(name="a.mp3"))
                self.assertEqual(answer.status_code, 200)
                self.assertEqual(answer.headers["Cache-Control"], "private, no-store")

    def test_hiding_an_item_locks_its_files_straight_away(self):
        self.sign_in()
        route = self.FILE_ROUTES[-1].format(name="a.mp3")
        self.assertEqual(self.client.get(route).status_code, 200)
        self.hidden = {"a.mp3"}
        self.assertEqual(self.client.post("/api/hidden/hide", json={"names": ["a.mp3"]}).status_code, 200)
        self.assertEqual(self.client.get(route).status_code, 404)

    def test_changing_hidden_items_waits_for_the_pin_but_hiding_does_not(self):
        self.sign_in()
        self.assertEqual(self.client.post("/api/hidden/restore", json={"names": ["a.mp3"]}).status_code, 423)
        self.assertEqual(self.client.post("/api/hidden/delete", json={"names": ["a.mp3"]}).status_code, 423)
        self.assertEqual(self.client.post("/api/hidden/hide", json={"names": ["a.mp3"]}).status_code, 200)
        self.unlock()
        self.assertEqual(self.client.post("/api/hidden/restore", json={"names": ["a.mp3"]}).status_code, 200)

    def test_files_are_refused_when_hidden_items_cannot_be_checked(self):
        self.sign_in()
        self.gateway.pin.forget_names("owner")
        original = self.gateway.backend._transport
        self.gateway.backend._transport = httpx.MockTransport(lambda request: httpx.Response(503))
        self.addCleanup(setattr, self.gateway.backend, "_transport", original)
        self.assertEqual(self.client.get(self.FILE_ROUTES[-1].format(name="b b.wav")).status_code, 502)


if __name__ == "__main__":
    unittest.main()
