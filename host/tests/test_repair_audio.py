"""repair_audio.sh and its helper route, with docker and wsl.exe replaced by stubs.

Run from the repository root: python3 -m unittest discover host/tests
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HOST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOST))
from speaker_helper import AudioRepair, SpeakerHandler  # noqa: E402

# ffmpeg passes once the flag file exists; recreating the container makes it exist if the socket does.
DOCKER = """#!/bin/sh
echo "docker $*" >> "$CALLS"
case "$*" in
  "compose ps -q mcp") echo abc ;;
  "exec "*) [ -e "$AUDIO_OK" ] ;;
  "compose up "*) [ -S "$PULSE_SOCKET" ] && [ -z "$RECREATE_BREAKS" ] && touch "$AUDIO_OK"; exit 0 ;;
  "inspect "*) echo healthy ;;
esac
"""
# rmdir really removes; pkill makes the socket WSLg would make.
WSL = """#!/usr/bin/env python3
import os, socket, sys
args = sys.argv[1:]
open(os.environ["CALLS"], "a").write("wsl " + " ".join(args) + "\\n")
if "rmdir" in args:
    os.rmdir(args[-1])
if "pkill" in args and not os.environ.get("NO_SOCKET"):
    socket.socket(socket.AF_UNIX).bind(os.environ["PULSE_SOCKET"])
"""


class Script(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        for name, body in (("docker", DOCKER), ("wsl.exe", WSL), ("wslpath", "#!/bin/sh\necho '\\\\wsl.localhost\\Ubuntu\\'\n")):
            path = bin_dir / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.socket = self.dir / "PulseServer"
        self.calls = self.dir / "calls"
        self.audio_ok = self.dir / "audio_ok"
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "PULSE_SOCKET": str(self.socket),
            "CALLS": str(self.calls),
            "AUDIO_OK": str(self.audio_ok),
            "RECREATE_BREAKS": "",
            "WSL_DISTRO_NAME": "Ubuntu",
            "REPAIR_SOCKET_WAIT_SECONDS": "2",
            "REPAIR_HEALTH_WAIT_SECONDS": "2",
            "REPAIR_RECREATE_DELAY_SECONDS": "0",
        }

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(HOST / "repair_audio.sh"), *args], env=self.env, capture_output=True, text=True, timeout=30
        )

    def called(self) -> str:
        return self.calls.read_text() if self.calls.exists() else ""

    def make_socket(self) -> None:
        import socket

        server = socket.socket(socket.AF_UNIX)
        self.addCleanup(server.close)
        server.bind(str(self.socket))

    def test_changes_nothing_when_audio_works(self) -> None:
        self.audio_ok.touch()
        result = self.run_script()
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("wsl", self.called())
        self.assertNotIn("compose up", self.called())

    def test_repairs_the_directory_docker_made(self) -> None:
        self.socket.mkdir()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("REPAIRED", result.stdout)
        calls = self.called()
        self.assertLess(calls.index("rmdir"), calls.index("pkill"))
        self.assertLess(calls.index("pkill"), calls.index("compose up"))
        self.assertTrue(self.socket.is_socket())

    def test_only_recreates_the_container_when_the_socket_is_fine(self) -> None:
        self.make_socket()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("wsl", self.called())
        self.assertIn("compose up", self.called())

    def test_leaves_a_directory_with_files_alone(self) -> None:
        self.socket.mkdir()
        (self.socket / "keep").touch()
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.socket / "keep").exists())
        self.assertNotIn("wsl", self.called())
        self.assertNotIn("compose up", self.called())

    def test_check_changes_nothing(self) -> None:
        self.socket.mkdir()
        result = self.run_script("--check")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.socket.is_dir())
        self.assertNotIn("wsl", self.called())
        self.assertNotIn("compose up", self.called())

    def test_reports_when_the_socket_never_comes_back(self) -> None:
        self.socket.mkdir()
        self.env["NO_SOCKET"] = "1"
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("wsl --shutdown", result.stdout)
        self.assertNotIn("compose up", self.called())

    def test_reports_when_audio_still_fails(self) -> None:
        self.make_socket()
        self.env["RECREATE_BREAKS"] = "1"
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAILED", result.stdout)


class Route(unittest.TestCase):
    TOKEN = "t" * 32

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.script = self.dir / "fake.sh"
        self.script.write_text("#!/bin/sh\necho step one\necho x >> \"$0.runs\"\nsleep 0.3\nexit ${FAKE_EXIT:-0}\n")
        self.script.chmod(0o755)
        SpeakerHandler.repair = AudioRepair(self.script)
        SpeakerHandler.token = self.TOKEN
        SpeakerHandler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SpeakerHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method: str, token: str | None = None) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}/audio/repair",
            method=method,
            data=b"{}" if method == "POST" else None,
            headers={"Authorization": f"Bearer {token or self.TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_needs_the_token(self) -> None:
        for method in ("GET", "POST"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request(method, "wrong")
            self.assertEqual(caught.exception.code, 401)
        self.assertFalse(Path(f"{self.script}.runs").exists())

    def test_runs_one_repair_at_a_time_and_reports_it(self) -> None:
        self.assertEqual(self.request("GET")["state"], "not_run")
        self.assertEqual(self.request("POST")["state"], "running")
        self.assertEqual(self.request("POST")["state"], "running")
        deadline = time.monotonic() + 5
        while (status := self.request("GET"))["state"] == "running" and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(status, {"state": "finished", "log": ["step one"]})
        self.assertEqual(Path(f"{self.script}.runs").read_text().count("x"), 1)

    def test_reports_a_failed_repair(self) -> None:
        self.script.write_text("#!/bin/sh\necho FAILED: nope\nexit 1\n")
        self.request("POST")
        deadline = time.monotonic() + 5
        while (status := self.request("GET"))["state"] == "running" and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(status, {"state": "failed", "log": ["FAILED: nope"]})


if __name__ == "__main__":
    unittest.main()
