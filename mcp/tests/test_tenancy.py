"""Who a request acts for: the rules that keep one person's data from another."""

import asyncio
import contextvars
import os
import threading
import unittest
from unittest import mock

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core import tenancy
from app.transport.luna_mcp import LunaMCP, RestUsers, SentiaTokenVerifier

TOKEN = "t" * 32
COMPANION = "c" * 32
RESOURCE = "https://app.example/mcp"


class WithoutTestUser(unittest.TestCase):
    def setUp(self) -> None:
        self.saved = tenancy._test_user
        tenancy._test_user = None
        self.addCleanup(setattr, tenancy, "_test_user", self.saved)


class IdentityTests(WithoutTestUser):
    def test_no_user_fails_rather_than_choosing_one(self) -> None:
        with self.assertRaises(tenancy.NoUserError):
            tenancy.current()
        with self.assertRaises(tenancy.NoUserError):
            tenancy.space_name()

    def test_ids_cannot_reach_outside_a_schema_or_folder(self) -> None:
        for bad in ("", "../owner", "a b", 'x"; DROP', "A", "x" * 33, None, 5):
            self.assertFalse(tenancy.is_valid(bad), bad)
            with self.assertRaises(ValueError), tenancy.acting_as(bad):
                pass
        self.assertEqual(tenancy.space_name("ab12"), "u_ab12")

    def test_acting_as_is_undone_and_new_threads_start_empty(self) -> None:
        seen = []

        def look() -> None:
            try:
                seen.append(tenancy.current())
            except tenancy.NoUserError:
                seen.append(None)

        with tenancy.acting_as("ab12"):
            self.assertEqual(tenancy.current(), "ab12")
            plain = threading.Thread(target=look)
            plain.start()
            plain.join()
            carried = threading.Thread(target=contextvars.copy_context().run, args=(look,))
            carried.start()
            carried.join()
        self.assertEqual(seen, [None, "ab12"])
        with self.assertRaises(tenancy.NoUserError):
            tenancy.current()

    def test_only_the_owner_passes_the_owner_check(self) -> None:
        with tenancy.acting_as(tenancy.OWNER):
            tenancy.require_owner("Speakers")
        with tenancy.acting_as("ab12"), self.assertRaises(PermissionError):
            tenancy.require_owner("Speakers")

    def test_per_user_keeps_state_apart(self) -> None:
        class Counter:
            def __init__(self) -> None:
                self.value = 0

            def add(self) -> int:
                self.value += 1
                return self.value

        shared = tenancy.PerUser(Counter)
        with tenancy.acting_as("one"):
            shared.add()
            self.assertEqual(shared.add(), 2)
        with tenancy.acting_as("two"):
            self.assertEqual(shared.add(), 1)


class DeletedPersonTests(WithoutTestUser):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(tenancy._removed.discard, "gone")

    def test_nothing_runs_for_a_deleted_person_even_mid_request(self) -> None:
        with tenancy.acting_as("gone"):
            tenancy.forbid("gone")
            with self.assertRaises(tenancy.NoUserError):
                tenancy.current()
        with self.assertRaises(tenancy.NoUserError), tenancy.acting_as("gone"):
            pass

    def test_the_owner_cannot_be_deleted(self) -> None:
        with self.assertRaises(ValueError):
            tenancy.forbid(tenancy.OWNER)
        with self.assertRaises(ValueError):
            tenancy.forbid("../x")


class UILinkTests(unittest.TestCase):
    def link(self, address: str):
        with mock.patch.dict(os.environ, {"LUNA_SSO_URL": "https://auth.example", "UI_PUBLIC_URL": address}):
            server = LunaMCP("Test", app="test", public_url="https://app.example", api_token=TOKEN, remove_user=print)
        return server._tool_manager.get_tool("get_ui_link").fn

    def test_the_tool_gives_the_public_address(self) -> None:
        self.assertEqual(self.link("https://app.example/ ")(), {"app": "Test", "url": "https://app.example"})

    def test_an_unset_address_is_said_plainly(self) -> None:
        with self.assertRaisesRegex(ValueError, "UI_PUBLIC_URL"):
            self.link("")()


class DeleteRouteTests(WithoutTestUser):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(os.environ.pop, "LUNA_SSO_URL", None)
        os.environ["LUNA_SSO_URL"] = "https://auth.example"
        self.removed = []
        server = LunaMCP("Test", app="test", public_url="https://app.example", api_token=TOKEN, remove_user=self.removed.append)
        self.client = TestClient(server.streamable_http_app(), raise_server_exceptions=False)

    def delete(self, target: str, user: str = "owner", token: str = TOKEN):
        return self.client.delete(f"/api/users/{target}", headers={"Authorization": f"Bearer {token}", "X-Luna-User": user})

    def test_only_the_owner_with_the_private_token_can_delete(self) -> None:
        self.assertEqual(self.delete("ab12").status_code, 200)
        self.assertEqual(self.removed, ["ab12"])
        self.assertEqual(self.delete("cd34", user="ab12").status_code, 403)
        self.assertEqual(self.delete("cd34", token="w" * 32).status_code, 401)
        self.assertEqual(self.client.delete("/api/users/cd34").status_code, 401)
        self.assertEqual(self.removed, ["ab12"])

    def test_the_owner_cannot_be_removed_through_it(self) -> None:
        self.assertEqual(self.delete("owner").status_code, 400)
        self.assertEqual(self.removed, [])

    def test_mcp_needs_sign_in_on_this_server(self) -> None:
        self.assertEqual(self.client.post("/mcp", json={}).status_code, 401)


class RestUserTests(WithoutTestUser):
    def client(self) -> TestClient:
        async def whoami(request):
            return JSONResponse({"user": tenancy.current()})

        app = Starlette(
            routes=[
                Route("/api/thing", whoami),
                Route("/api/metadata", whoami),
                Route("/api/public/x", lambda request: JSONResponse({"open": True})),
                Route("/health", lambda request: JSONResponse({"ok": True})),
            ]
        )
        wrapped = RestUsers(app, TOKEN, COMPANION, ("/api/public/",))
        return TestClient(wrapped, raise_server_exceptions=False)

    def headers(self, token: str = TOKEN, user: str | None = "ab12") -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", **({"X-Luna-User": user} if user else {})}

    def test_the_named_user_is_who_the_route_acts_for(self) -> None:
        self.assertEqual(self.client().get("/api/thing", headers=self.headers()).json(), {"user": "ab12"})

    def test_no_or_wrong_token_is_refused(self) -> None:
        client = self.client()
        self.assertEqual(client.get("/api/thing", headers={"X-Luna-User": "owner"}).status_code, 401)
        self.assertEqual(client.get("/api/thing", headers=self.headers("wrong" * 8)).status_code, 401)

    def test_a_token_without_a_valid_user_is_refused(self) -> None:
        client = self.client()
        self.assertEqual(client.get("/api/thing", headers=self.headers(user=None)).status_code, 400)
        self.assertEqual(client.get("/api/thing", headers=self.headers(user="../x")).status_code, 400)

    def test_the_companion_token_only_reaches_companion_routes(self) -> None:
        client = self.client()
        self.assertEqual(client.get("/api/metadata", headers=self.headers(COMPANION)).status_code, 200)
        self.assertEqual(client.get("/api/thing", headers=self.headers(COMPANION)).status_code, 401)
        self.assertEqual(client.post("/api/metadata", headers=self.headers(COMPANION)).status_code, 401)

    def test_open_paths_and_non_api_routes_need_nothing(self) -> None:
        client = self.client()
        self.assertEqual(client.get("/api/public/x").status_code, 200)
        self.assertEqual(client.get("/health").status_code, 200)


class VerifierTests(unittest.TestCase):
    def verify(self, answer, status: int = 200, verifier_resource: str = RESOURCE):
        calls = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(status, json=answer)

        verifier = SentiaTokenVerifier("http://sentia:8000", verifier_resource, httpx.MockTransport(respond))
        return asyncio.run(verifier.verify_token("secret")), calls

    def test_an_active_token_names_its_user(self) -> None:
        access, _ = self.verify({"active": True, "sub": "ab12", "client_id": "c", "resource": RESOURCE, "exp": 4000000000})
        self.assertEqual(access.subject, "ab12")

    def test_refusals(self) -> None:
        for answer, status in (
            ({"active": False}, 200),
            ({"active": True, "sub": "../x"}, 200),
            ({"active": True}, 200),
            ({"active": True, "sub": "ab12", "resource": "https://other.example/mcp"}, 200),
            ({}, 500),
        ):
            self.assertIsNone(self.verify(answer, status)[0], answer)

    def test_a_hidden_app_refuses_the_people_it_is_hidden_from(self) -> None:
        def verify(hidden):
            respond = lambda request: httpx.Response(200, json={"active": True, "sub": "ab12", "hidden_apps": hidden})
            verifier = SentiaTokenVerifier("http://sentia:8000", RESOURCE, httpx.MockTransport(respond), app="lumia")
            return asyncio.run(verifier.verify_token("secret"))

        self.assertIsNone(verify(["lumia"]))
        self.assertIsNotNone(verify(["vibia"]))

    def test_a_token_is_only_asked_about_once_in_a_while(self) -> None:
        calls = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"active": True, "sub": "ab12", "exp": 4000000000})

        verifier = SentiaTokenVerifier("http://sentia:8000", RESOURCE, httpx.MockTransport(respond))

        async def twice():
            return await verifier.verify_token("secret"), await verifier.verify_token("secret")

        first, second = asyncio.run(twice())
        self.assertEqual((first.subject, second.subject, len(calls)), ("ab12", "ab12", 1))


if __name__ == "__main__":
    unittest.main()
