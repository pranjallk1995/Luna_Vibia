"""Let the Vibia MCP container choose a Windows Bluetooth speaker; runs on the WSL host.

The container cannot reach Windows, so this small service lists Windows'
connected Bluetooth speakers and makes one the default output through
PowerShell (windows_audio.ps1). WSLg's audio follows Windows' default output,
so Vibia, playing through WSLg, is then heard on that speaker. It also reads
and sets that output's volume, which a Bluetooth speaker follows.

Standard library only. Requests need ``Authorization: Bearer <LUNAVIBIA_API_TOKEN>``.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().with_name("windows_audio.ps1")
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
POWERSHELL_TIMEOUT_SECONDS = 60
# A speaker can only be selected by an ID a recent listing returned.
LISTING_MAX_AGE_SECONDS = 300
# The UI polls the current output; answers this fresh are reused instead of asking Windows again.
DEFAULT_MAX_AGE_SECONDS = 5
# An output missing from the listing (say, wired) is listed again only after this long, to
# notice a speaker that just connected without paying a 5-second listing on every read.
UNLISTED_RECHECK_SECONDS = 30
ENDPOINT_ID = re.compile(r"^\{0\.0\.0\.[0-9a-f]{8}\}\.\{[0-9a-f-]{36}\}$")


class SpeakerError(RuntimeError):
    """Raised when Windows cannot list or switch its speakers."""


class WindowsSpeakers:
    """Windows' connected Bluetooth speakers, read and switched through PowerShell."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listed: dict[str, dict[str, Any]] = {}
        self._listed_at = 0.0
        self._default: dict[str, Any] | None = None
        self._default_at = 0.0
        # One volume change at a time, so two quick "louder"s add up.
        self._volume_lock = threading.Lock()
        self._script = subprocess.run(
            ["wslpath", "-w", str(SCRIPT)], capture_output=True, text=True, check=True
        ).stdout.strip()

    def _run(self, *args: str) -> Any:
        try:
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", self._script, *args],
                capture_output=True, text=True, timeout=POWERSHELL_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SpeakerError(f"PowerShell could not be run: {error}") from error
        if result.returncode != 0:
            lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
            raise SpeakerError(lines[0] if lines else f"PowerShell exited with {result.returncode}.")
        return json.loads(result.stdout or "[]")

    def list(self) -> list[dict[str, Any]]:
        speakers = self._run("list")
        with self._lock:
            self._listed = {speaker["id"]: speaker for speaker in speakers}
            self._listed_at = time.monotonic()
            self._default = None
        return speakers

    def default(self) -> dict[str, Any]:
        """Windows' current default output, and whether it is a connected Bluetooth speaker.

        Windows may switch it on its own, for example when a Bluetooth speaker
        connects, so this asks Windows rather than trusting the last selection.
        """
        with self._lock:
            if self._default is not None and time.monotonic() - self._default_at < DEFAULT_MAX_AGE_SECONDS:
                return self._default
        output = self._run("default")
        with self._lock:
            age = time.monotonic() - self._listed_at
            known = output["id"] in self._listed
        if output["id"] and (age >= LISTING_MAX_AGE_SECONDS or (not known and age >= UNLISTED_RECHECK_SECONDS)):
            self.list()
        with self._lock:
            output = {**output, "bluetooth": output["id"] in self._listed}
            self._default, self._default_at = output, time.monotonic()
        return output

    def select(self, endpoint_id: str) -> dict[str, Any]:
        endpoint_id = endpoint_id.strip().lower()
        if not ENDPOINT_ID.match(endpoint_id):
            raise ValueError("id must be a speaker ID returned by GET /speakers.")
        with self._lock:
            fresh = time.monotonic() - self._listed_at < LISTING_MAX_AGE_SECONDS
            speaker = self._listed.get(endpoint_id) if fresh else None
        if speaker is None:
            speaker = next((item for item in self.list() if item["id"] == endpoint_id), None)
        if speaker is None:
            raise LookupError(f"No connected Bluetooth speaker has ID {endpoint_id}.")
        if self._run("set", endpoint_id)["id"] != endpoint_id:
            raise SpeakerError(f"Windows did not switch its output to {speaker['description']}.")
        with self._lock:
            self._default = None
        return {**speaker, "default": True}


    def volume(self) -> dict[str, Any]:
        """The default output's volume (0-100), whether it is muted, and which output it is."""
        return self._with_output(self._run("volume"))

    def set_volume(
        self, percent: int | None = None, change: int | None = None, muted: bool | None = None
    ) -> dict[str, Any]:
        """Set the volume (``percent``) or move it (``change``, + louder), and/or mute it."""
        for label, value, low, high in (("percent", percent, 0, 100), ("change", change, -100, 100)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high):
                raise ValueError(f"{label} must be a whole number from {low} to {high}.")
        if percent is not None and change is not None:
            raise ValueError("Send percent or change, not both.")
        if muted is not None and not isinstance(muted, bool):
            raise ValueError("muted must be true or false.")
        if percent is None and change is None and muted is None:
            raise ValueError("Send percent, change, or muted.")
        with self._volume_lock:
            state = None
            if change is not None:
                percent = self._run("volume")["volume"] + change
            if percent is not None:
                state = self._run("set-volume", str(max(0, min(100, percent))))
            if muted is not None:
                state = self._run("set-mute", "true" if muted else "false")
        return self._with_output(state)

    def _with_output(self, state: dict[str, Any]) -> dict[str, Any]:
        output = self.default()
        return {
            "volume": state["volume"], "muted": state["muted"],
            "name": output["name"], "description": output["description"], "bluetooth": output["bluetooth"],
        }


class SpeakerHandler(BaseHTTPRequestHandler):
    speakers: WindowsSpeakers
    token: str

    def _send(self, status: int, body: Any) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if hmac.compare_digest(supplied.encode(), self.token.encode()):
            return True
        self._send(401, {"detail": "Missing or invalid token."})
        return False

    def _handle(self, action) -> None:
        try:
            self._send(200, action())
        except ValueError as error:
            self._send(400, {"detail": str(error)})
        except LookupError as error:
            self._send(404, {"detail": str(error)})
        except SpeakerError as error:
            self._send(502, {"detail": str(error)})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/speakers":
            if self._authorized():
                self._handle(lambda: {"speakers": self.speakers.list()})
        elif self.path == "/speakers/default":
            if self._authorized():
                self._handle(self.speakers.default)
        elif self.path == "/speakers/volume":
            if self._authorized():
                self._handle(self.speakers.volume)
        else:
            self._send(404, {"detail": "Not found."})

    def _body(self) -> dict[str, Any] | None:
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 4096)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._send(400, {"detail": "Send a JSON object."})
            return None
        return body

    def do_POST(self) -> None:
        if self.path not in ("/speakers/default", "/speakers/volume"):
            self._send(404, {"detail": "Not found."})
            return
        if not self._authorized():
            return
        body = self._body()
        if body is None:
            return
        if self.path == "/speakers/default":
            self._handle(lambda: self.speakers.select(str(body.get("id", ""))))
        else:
            self._handle(lambda: self.speakers.set_volume(body.get("percent"), body.get("change"), body.get("muted")))

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    token = os.environ.get("LUNAVIBIA_API_TOKEN", "").strip()
    if len(token) < 32:
        raise SystemExit("LUNAVIBIA_API_TOKEN must contain at least 32 characters.")
    host = os.environ.get("LUNAVIBIA_SPEAKER_HELPER_HOST", "0.0.0.0")
    port = int(os.environ.get("LUNAVIBIA_SPEAKER_HELPER_PORT", "18007"))
    SpeakerHandler.speakers = WindowsSpeakers()
    SpeakerHandler.token = token
    print(f"Luna Vibia speaker helper listening on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), SpeakerHandler).serve_forever()


if __name__ == "__main__":
    main()
