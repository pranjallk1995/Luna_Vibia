"""Play tracks on the host's speakers through its PulseAudio (or PipeWire) server."""

from __future__ import annotations

import re
import subprocess
import threading
import time
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

    def _request(self, method: str, path: str, timeout: float | None = None, **kwargs: Any) -> Any:
        try:
            response = httpx.request(
                method, f"{self.url}{path}", headers=self.headers, timeout=timeout or self.timeout, **kwargs
            )
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

    def current(self) -> Row | None:
        """Windows' output right now; it may have switched on its own since playback started."""
        output = self._request("GET", "/speakers/default", timeout=AppConfig.SPEAKER_OUTPUT_TIMEOUT_SECONDS)
        if not output.get("id"):
            return None
        return {"name": output["name"], "description": output["description"], "bluetooth": output["bluetooth"]}


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
        self._queue: list[tuple[str, Path]] = []
        # When the current track's second 0 played; its position is the time since.
        self._track_started = 0.0

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

    def _route(self, speaker: Speaker) -> str | None:
        """Send sound to ``speaker``; return the sink to name (None: the default sink)."""
        if self.windows is None:
            return speaker.name
        if not speaker.default:
            self.windows.select(speaker)
        return None

    def play(self, queue: list[tuple[str, Path]], speaker: Speaker, loop: bool) -> Row:
        """Start playing ``queue`` (track name, file) in order on ``speaker``."""
        sink = self._route(speaker)
        self.stop()
        return self._start(queue, sink, speaker, loop, 0, 0.0)

    def switch(self, speaker: Speaker) -> Row:
        """Move the playing queue to ``speaker``, resuming the current track at the same second."""
        if self.status()["status"] != "playing":
            raise ValueError("Nothing is playing; start a queue with play_tracks.")
        sink = self._route(speaker)
        with self._lock:
            # Read after switching: the music kept playing while Windows changed output.
            state, queue = dict(self._state), list(self._queue)
            position = time.monotonic() - self._track_started
        if state["status"] != "playing":
            raise ValueError("The queue finished before the speaker changed; start it again with play_tracks.")
        self.stop()
        track = state["tracks"].index(state["now_playing"])
        return self._start(queue, sink, speaker, state["loop"], track, position)

    def _start(
        self, queue: list[tuple[str, Path]], sink: str | None, speaker: Speaker, loop: bool,
        track: int, seconds: float,
    ) -> Row:
        with self._lock:
            self._stop = threading.Event()
            self._queue = list(queue)
            self._track_started = time.monotonic() - seconds
            self._state = {
                "status": "playing",
                "speaker": speaker.as_row(),
                "tracks": [name for name, _ in queue],
                "loop": loop,
                "now_playing": queue[track][0],
            }
            self._thread = threading.Thread(
                target=self._run, args=(queue, sink, loop, self._stop, track, seconds), daemon=True
            )
            self._thread.start()
        return self.status()

    def _command(self, path: Path, sink: str | None, name: str, seconds: float = 0.0) -> list[str]:
        """The ffmpeg command playing ``path`` from ``seconds`` on ``sink`` (None: the default sink)."""
        # -re feeds the sound server in real time: unpaced, ffmpeg fills the server's
        # buffer and exits seconds early, so the status runs ahead and a stop or the
        # next track can cut off the tail.
        device = ["-device", sink] if sink else []
        seek = ["-ss", f"{seconds:.2f}"] if seconds > 0 else []
        return [
            "ffmpeg", "-v", "error", "-nostdin", "-re", *seek, "-i", str(path),
            "-f", "pulse", "-name", self.CLIENT_NAME, *device, name,
        ]

    def _run(
        self, queue: list[tuple[str, Path]], sink: str | None, loop: bool, stop: threading.Event,
        track: int = 0, seconds: float = 0.0,
    ) -> None:
        """Play ``queue`` from ``seconds`` into track ``track``; repeats start from the top."""
        while True:
            for name, path in queue[track:]:
                with self._lock:
                    if stop.is_set():
                        return
                    self._state["now_playing"] = name
                    self._track_started = time.monotonic() - seconds
                    process = self._process = subprocess.Popen(
                        self._command(path, sink, name, seconds),
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
                seconds = 0.0
            track = 0
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
            state = dict(self._state)
            if state["status"] == "playing":
                position = time.monotonic() - self._track_started
                state["position_seconds"] = round(position, 1)
                # When the current track's second 0 played, as a Unix time: other apps on
                # this host (Luna Lumia's beat pulses) follow the track with their own clock.
                state["started_at"] = round(time.time() - position, 3)
            return state

    def output(self, playing_on: Row | None = None) -> Row | None:
        """Where sound goes now: Windows' live default, else the playing (or default) sink."""
        if self.windows is not None:
            return self.windows.current()
        if playing_on is not None:
            return playing_on
        default = next((speaker for speaker in self.speakers() if speaker.default), None)
        return default.as_row() if default else None

    def live_status(self) -> Row:
        """The status with ``output``, the speaker sound actually reaches now.

        Windows can move its output (for example when another Bluetooth speaker
        connects), so while playing, ``speaker`` reports that live output and
        ``requested_speaker`` the one chosen when playback started.
        """
        status = self.status()
        playing = status["status"] == "playing"
        try:
            output = self.output(status.get("speaker") if playing else None)
        except SpeakerUnavailableError as error:
            return {**status, "output": None, "output_error": str(error)}
        status["output"] = output
        chosen = status.get("speaker")
        if playing and chosen and output and output["name"] != chosen["name"]:
            status["speaker"] = output
            status["requested_speaker"] = chosen
            status["note"] = (
                f"The host's output changed to {output['description']} after playback started, so "
                f"the music now plays there. To move it back, call switch_speaker with speaker "
                f"{chosen['name']!r}."
            )
        return status
