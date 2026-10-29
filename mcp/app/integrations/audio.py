"""Read audio files with ffprobe and ffmpeg, and measure tempo, key, and energy."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import numpy as np

from app.core.config import AppConfig

Row = dict[str, Any]


class AudioToolError(ValueError):
    """Raised when ffprobe or ffmpeg cannot read the bytes as audio."""


def run_tool(command: list[str], data: bytes) -> bytes:
    """Run ffprobe or ffmpeg on ``data`` (fed on stdin) and return its stdout."""
    try:
        result = subprocess.run(
            command, input=data, capture_output=True, timeout=AppConfig.AUDIO_TOOL_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as error:
        raise AudioToolError("Reading the audio took too long.") from error
    if result.returncode != 0:
        raise AudioToolError("Content is not readable audio.")
    return result.stdout


class AudioProbe:
    """Describe an audio file: container, stream, duration, and embedded tags."""

    # ffprobe's format names for the containers Vibia stores.
    FORMATS = {
        "mp3": "MP3",
        "wav": "WAV",
        "flac": "FLAC",
        "ogg": "OGG",
        "mov,mp4,m4a,3gp,3g2,mj2": "M4A",
    }

    def probe(self, data: bytes) -> Row:
        output = run_tool(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "pipe:0"],
            data,
        )
        try:
            info = json.loads(output)
        except json.JSONDecodeError as error:
            raise AudioToolError("Content is not readable audio.") from error
        stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        if stream is None:
            raise AudioToolError("Content has no audio stream.")
        container = info.get("format", {})
        tags = {key.lower(): value for key, value in {**container.get("tags", {}), **stream.get("tags", {})}.items()}
        duration = container.get("duration") or stream.get("duration")
        return {
            "format": self.FORMATS.get(container.get("format_name", ""), container.get("format_name", "").upper()),
            "codec": stream.get("codec_name"),
            "duration_seconds": round(float(duration), 2) if duration not in (None, "N/A") else None,
            "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
            "channels": stream.get("channels"),
            "bitrate": int(container["bit_rate"]) if container.get("bit_rate") not in (None, "N/A") else None,
            "tags": tags,
        }

    def decode(self, data: bytes, sample_rate: int) -> np.ndarray:
        """Decode to mono float32 samples at ``sample_rate``."""
        pcm = run_tool(
            ["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "pipe:1"],
            data,
        )
        samples = np.frombuffer(pcm, dtype=np.float32)
        if not samples.size:
            raise AudioToolError("The audio decoded to silence of zero length.")
        return samples


class MusicFeatures:
    """Tempo, key, and energy of a track, measured from its sound with librosa."""

    KEYS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    # Krumhansl-Schmuckler key profiles: how strongly each scale degree is heard.
    MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    @staticmethod
    def middle(samples: np.ndarray, sample_rate: int, seconds: int) -> np.ndarray:
        """The central ``seconds`` of a track, skipping intros and fade-outs."""
        length = seconds * sample_rate
        if samples.size <= length:
            return samples
        start = (samples.size - length) // 2
        return samples[start : start + length]

    @classmethod
    def key(cls, chroma: np.ndarray) -> str | None:
        profile = chroma.mean(axis=1)
        if not np.any(profile):
            return None
        best = max(
            ((np.corrcoef(profile, np.roll(template, shift))[0, 1], shift, mode)
             for mode, template in (("major", cls.MAJOR), ("minor", cls.MINOR))
             for shift in range(12)),
            key=lambda candidate: candidate[0],
        )
        return f"{cls.KEYS[best[1]]} {best[2]}"

    def measure(self, samples: np.ndarray, sample_rate: int) -> Row:
        import librosa  # heavy import, only needed while analyzing

        excerpt = self.middle(samples, sample_rate, AppConfig.FEATURE_MAX_SECONDS)
        tempo, _ = librosa.beat.beat_track(y=excerpt, sr=sample_rate)
        tempo = float(np.atleast_1d(tempo)[0])
        chroma = librosa.feature.chroma_cqt(y=excerpt, sr=sample_rate)
        rms = float(np.sqrt(np.mean(np.square(excerpt))))
        return {
            "tempo_bpm": round(tempo, 1) if tempo > 0 else None,
            "musical_key": self.key(chroma),
            # RMS of full-scale audio rarely exceeds ~0.3; scale so typical music spans 0-1.
            "energy": round(min(rms / 0.3, 1.0), 3),
        }
