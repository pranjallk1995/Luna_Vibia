"""Play tracks on the host's speakers through its PulseAudio (or PipeWire) server."""

from __future__ import annotations

import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import AppConfig

Row = dict[str, Any]


class SpeakerUnavailableError(RuntimeError):
    """Raised when the host's sound server cannot be reached."""


@dataclass(frozen=True)
class Speaker:
    """One audio output on the host: a PulseAudio sink, or a Windows endpoint (``id``)."""

    name: str
    description: str
    default: bool
    id: str = ""

    def as_row(self) -> Row:
        return {"name": self.name, "description": self.description, "default": self.default}


class WindowsSpeakerHelper:
    """Windows' connected Bluetooth speakers, through the WSL host's speaker helper.

    Under WSL the container sees a single sound output, WSLg's, which plays on
    Windows' default output. The helper (host/speaker_helper.py) lists Windows'
    Bluetooth speakers and switches that default, so playback follows.
    """

    def __init__(self, url: str, token: str, timeout: float = AppConfig.SPEAKER_HELPER_TIMEOUT_SECONDS) -> None:
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = httpx.request(method, f"{self.url}{path}", headers=self.headers, timeout=self.timeout, **kwargs)
        except httpx.HTTPError as error:
            raise SpeakerUnavailableError(
                f"The Windows speaker helper is not reachable at {self.url}; start it on the host "
                "with: systemctl --user start luna-vibia-speakers"
            ) from error
        if response.is_error:
            try:
                detail = response.json()["detail"]
            except (ValueError, KeyError):
                detail = response.text
            raise SpeakerUnavailableError(f"The Windows speaker helper failed: {detail}")
        return response.json()

    def speakers(self) -> list[Speaker]:
        rows = self._request("GET", "/speakers")["speakers"]
        if not rows:
            raise SpeakerUnavailableError(
                "No Bluetooth speaker is connected to Windows. Connect one and try again."
            )
        return [Speaker(row["name"], row["description"], bool(row["default"]), row["id"]) for row in rows]

    def select(self, speaker: Speaker) -> None:
        """Make ``speaker`` Windows' default output, which WSLg's audio follows."""
        self._request("POST", "/speakers/default", json={"id": speaker.id})


class SpeakerPlayer:
    """List the host's audio outputs and play a queue of files on one of them.

    ffmpeg reaches the sound server named by ``PULSE_SERVER``: the host's socket,
    mounted into the container. With a Windows speaker helper, the speakers are
    Windows' Bluetooth outputs instead, and playing makes the chosen one Windows'
    default before playing on the default sink. One queue plays at a time;
    starting another stops the current one.
    """

    CLIENT_NAME = "Luna Vibia"
    # ffmpeg -sinks lists one output per line: "* name [description] (none)", "*" marking the default.
    SINK_LINE = re.compile(r"^\s*(?P<default>\*)?\s*(?P<name>\S+) \[(?P<description>.*)\](?: \([^)]*\))?\s*$")
    UNREACHABLE_MESSAGE = (
        "No speakers are reachable: the host's sound server is not running or its socket is "
        "not mounted. Set PULSE_SOCKET in .env and restart Vibia."
    )

    def __init__(self, windows: WindowsSpeakerHelper | None = None) -> None:
        self.windows = windows
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._state: Row = {"status": "idle"}

    @classmethod
    def parse_sinks(cls, output: str) -> list[Speaker]:
        speakers = []
        for line in output.splitlines():
            match = cls.SINK_LINE.match(line)
            if match:
                speakers.append(Speaker(match["name"], match["description"], bool(match["default"])))
        return speakers

    def speakers(self) -> list[Speaker]:
        """Return the host's audio outputs, rejecting an unreachable sound server."""
        if self.windows is not None:
            return self.windows.speakers()
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-sinks", "pulse"],
                capture_output=True,
                text=True,
                timeout=AppConfig.SPEAKER_LIST_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SpeakerUnavailableError(self.UNREACHABLE_MESSAGE) from error
        speakers = self.parse_sinks(result.stdout)
        if not speakers:
            raise SpeakerUnavailableError(self.UNREACHABLE_MESSAGE)
        return speakers

    def play(self, queue: list[tuple[str, Path]], speaker: Speaker, loop: bool) -> Row:
        """Start playing ``queue`` (track name, file) in order on ``speaker``."""
        sink: str | None = speaker.name
        if self.windows is not None:
            if not speaker.default:
                self.windows.select(speaker)
            sink = None
        self.stop()
        with self._lock:
            self._stop = threading.Event()
            self._state = {
                "status": "playing",
                "speaker": speaker.as_row(),
                "tracks": [name for name, _ in queue],
                "loop": loop,
                "now_playing": queue[0][0],
            }
            self._thread = threading.Thread(
                target=self._run, args=(queue, sink, loop, self._stop), daemon=True
            )
            self._thread.start()
        return self.status()

    def _command(self, path: Path, sink: str | None, name: str) -> list[str]:
        """The ffmpeg command playing ``path`` on ``sink`` (None: the default sink)."""
        # -re feeds the sound server in real time: unpaced, ffmpeg fills the server's
        # buffer and exits seconds early, so the status runs ahead and a stop or the
        # next track can cut off the tail.
        device = ["-device", sink] if sink else []
        return [
            "ffmpeg", "-v", "error", "-nostdin", "-re", "-i", str(path),
            "-f", "pulse", "-name", self.CLIENT_NAME, *device, name,
        ]

    def _run(self, queue: list[tuple[str, Path]], sink: str | None, loop: bool, stop: threading.Event) -> None:
        while True:
            for name, path in queue:
                with self._lock:
                    if stop.is_set():
                        return
                    self._state["now_playing"] = name
                    process = self._process = subprocess.Popen(
                        self._command(path, sink, name),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                _, error = process.communicate()
                if process.returncode != 0 and not stop.is_set():
                    detail = error.decode(errors="replace").strip().splitlines()
                    with self._lock:
                        self._state = {
                            "status": "failed",
                            "track": name,
                            "error": detail[-1] if detail else f"ffmpeg exited with {process.returncode}.",
                        }
                    return
            if not loop:
                break
        with self._lock:
            if not stop.is_set():
                self._state = {**self._state, "status": "finished", "now_playing": None}

    def stop(self) -> Row:
        """Stop the current queue, if any."""
        with self._lock:
            self._stop.set()
            process, thread = self._process, self._thread
            if process is not None and process.poll() is None:
                process.terminate()
            was_playing = self._state["status"] == "playing"
        if thread is not None:
            thread.join(timeout=AppConfig.PLAYBACK_STOP_TIMEOUT_SECONDS)
            if thread.is_alive() and process is not None:
                process.kill()
                thread.join()
        with self._lock:
            self._process = self._thread = None
            self._state = {"status": "idle"}
        return {"status": "stopped" if was_playing else "idle"}

    def status(self) -> Row:
        with self._lock:
            return dict(self._state)
