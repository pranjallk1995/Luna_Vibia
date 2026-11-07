"""In-memory test doubles for Luna Vibia repositories, models, and audio fixtures."""

import base64
import hashlib
import io
import subprocess
import sys
import wave
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.core.models import TrackDescription
from app.data.repositories import PUBLIC_TRACK_PATH
from app.integrations.speakers import Speaker, SpeakerPlayer
from app.integrations.visia import VisiaImageCatalog

SUMMARY_KEYS = (
    "name", "caption", "tags", "favorite", "duration_seconds", "tempo_bpm", "musical_key",
    "energy", "cover_url", "updated_at", "public_url",
)


class FakeTrackRepository:
    """Provide an in-memory TrackRepository test double."""

    def __init__(self) -> None:
        self.rows = {}
        self.beat_maps = {}

    def beats(self, content_sha256):
        return self.beat_maps.get(content_sha256)

    def save_beats(self, content_sha256, beat_map):
        self.beat_maps.setdefault(content_sha256, dict(beat_map))

    def upsert(self, record, public_base_url):
        previous = self.rows.get(record.name, {})
        track_id = previous.get("track_id", f"track-{len(self.rows) + 1}")
        fields = {key: value for key, value in asdict(record).items() if key not in ("facts", "embedding")}
        row = {
            **fields,
            **asdict(record.facts),
            "embedding": list(record.embedding),
            "tags": list(record.tags),
            "cover_url": previous.get("cover_url"),
            "updated_at": "test",
            "hidden": previous.get("hidden", False),
            "favorite": previous.get("favorite", False),
            "showcase_rank": previous.get("showcase_rank"),
            "track_id": track_id,
            "public_url": f"{public_base_url}{PUBLIC_TRACK_PATH}{track_id}",
        }
        self.rows[record.name] = row
        return self._public(row)

    @staticmethod
    def _public(row):
        return {key: value for key, value in row.items() if key not in ("embedding", "showcase_rank")}

    def _in_order(self, rows):
        return sorted(rows, key=lambda row: (row.get("showcase_rank") is not None, row.get("showcase_rank") or 0))

    def get(self, name, hidden=False):
        row = self.rows.get(name)
        if row is None or (hidden is not None and row["hidden"] != hidden):
            return None
        return self._public(row)

    def list(self, hidden=False):
        return [
            self._public(row)
            for row in self._in_order(self.rows.values())
            if hidden is None or row["hidden"] == hidden
        ]

    def list_favorites(self):
        return [self._public(row) for row in self._in_order(self.rows.values()) if row["favorite"] and not row["hidden"]]

    def is_hidden(self, name):
        if name not in self.rows:
            raise FileNotFoundError(name)
        return self.rows[name]["hidden"]

    def find_visible_by_content(self, content_sha256):
        return next(
            (
                self._public(row)
                for row in self.rows.values()
                if row["content_sha256"] == content_sha256 and not row["hidden"]
            ),
            None,
        )

    def user_of_track_id(self, identifier):
        return None

    def name_for_track_id(self, track_id):
        return next(
            (name for name, row in self.rows.items() if row["track_id"] == track_id), None
        )

    def delete(self, name):
        self.rows.pop(name, None)

    def rename(self, name, new_name):
        if new_name in self.rows:
            raise FileExistsError(new_name)
        row = self.rows.get(name)
        if row is None or row["hidden"]:
            raise FileNotFoundError(name)
        self.rows[new_name] = {**self.rows.pop(name), "name": new_name}
        return self._public(self.rows[new_name])

    def update_metadata(self, name, caption, tags, hidden=False):
        row = self.rows.get(name)
        if row is None or row["hidden"] != hidden:
            raise FileNotFoundError(name)
        row["caption"] = caption
        row["tags"] = tags
        return self._public(row)

    def set_cover(self, name, cover_url):
        row = self.rows.get(name)
        if row is None or row["hidden"]:
            raise FileNotFoundError(name)
        row["cover_url"] = cover_url
        return self._public(row)

    def embeddings(self, names):
        return {
            name: self.rows[name]["embedding"]
            for name in names
            if name in self.rows and not self.rows[name]["hidden"] and self.rows[name]["embedding"]
        }

    def showcase_candidates(self):
        visible = [row for row in self.rows.values() if not row["hidden"]]
        return [
            {"name": row["name"], "embedding": row.get("embedding"), "showcase_rank": row.get("showcase_rank")}
            for row in reversed(visible)
        ]

    def save_showcase_order(self, names):
        for row in self.rows.values():
            row["showcase_rank"] = None
        for rank, name in enumerate(names, 1):
            self.rows[name]["showcase_rank"] = rank

    def insert_showcase_rank(self, name, rank):
        for row in self.rows.values():
            if row.get("showcase_rank") is not None and row["showcase_rank"] >= rank:
                row["showcase_rank"] += 1
        self.rows[name]["showcase_rank"] = rank

    def clear_showcase_order(self):
        ranked = [row for row in self.rows.values() if row.get("showcase_rank") is not None]
        for row in ranked:
            row["showcase_rank"] = None
        return len(ranked)

    def set_hidden(self, names, hidden):
        changed = self._set_flag(names, "hidden", hidden, include_hidden=True)
        for name in changed:
            self.rows[name]["showcase_rank"] = None
        return changed

    def set_favorite(self, names, favorite):
        return self._set_flag(names, "favorite", favorite, include_hidden=False)

    def _set_flag(self, names, field, value, include_hidden):
        changed = []
        for name in names:
            row = self.rows.get(name)
            if row and (include_hidden or not row["hidden"]) and row[field] != value:
                row[field] = value
                changed.append(name)
        return changed

    def search(
        self, query, tags, match_all, limit, offset, query_embedding=None, semantic_weight=0.75,
        min_seconds=None, max_seconds=None,
    ):
        """Rank by embedding similarity when given one, else keep word matches."""
        stem = query.rstrip("s")
        candidates = []
        for row in self.rows.values():
            if row["hidden"]:
                continue
            if min_seconds is not None and row["duration_seconds"] < min_seconds:
                continue
            if max_seconds is not None and row["duration_seconds"] > max_seconds:
                continue
            words = bool(stem) and (stem in row["caption"].lower() or any(stem in tag for tag in row["tags"]))
            if tags and not (set(tags) <= set(row["tags"]) if match_all else set(tags) & set(row["tags"])):
                continue
            if query_embedding:
                similarity = float(np.dot(query_embedding, row["embedding"])) if row["embedding"] else 0.0
                score = semantic_weight * similarity + (1 - semantic_weight) * (0.5 if words else 0.0)
            elif stem and not words:
                continue
            else:
                score = 0.5 if words else 0.0
            candidates.append({**{key: row[key] for key in SUMMARY_KEYS}, "score": round(score, 4)})
        candidates.sort(key=lambda item: -item["score"])
        return len(candidates), candidates[offset : offset + limit]


class FakePlaylistRepository:
    """An in-memory PlaylistRepository: deleted tracks drop out, as the foreign key makes them."""

    def __init__(self, tracks: FakeTrackRepository) -> None:
        self.tracks = tracks
        self.playlists: dict[str, dict] = {}
        self.order: dict[str, list[str]] = {}

    def _track(self, track_id):
        return next((row for row in self.tracks.rows.values() if row["track_id"] == track_id), None)

    def _summary(self, playlist):
        rows = [self._track(track_id) for track_id in self.order[playlist["playlist_id"]]]
        visible = [row for row in rows if row and not row["hidden"]]
        return {**playlist, "track_count": len(visible),
                "duration_seconds": float(sum(row["duration_seconds"] or 0 for row in visible))}

    def list(self):
        return [self._summary(row) for row in sorted(self.playlists.values(), key=lambda row: row["name"].lower())]

    def get(self, name):
        row = next((row for row in self.playlists.values() if row["name"].lower() == name.lower()), None)
        return self._summary(row) if row else None

    def entries(self, playlist_id):
        rows = [self._track(track_id) for track_id in self.order[playlist_id]]
        return [{"position": index, **self.tracks._public(row)} for index, row in enumerate(filter(None, rows), start=1)]

    def _unique(self, name, playlist_id=None):
        clash = self.get(name)
        if clash and clash["playlist_id"] != playlist_id:
            raise ValueError(f"A playlist called {name!r} already exists.")

    def create(self, name, description):
        self._unique(name)
        playlist_id = f"playlist-{len(self.playlists) + 1}"
        self.playlists[playlist_id] = {"playlist_id": playlist_id, "name": name, "description": description,
                                       "created_at": "test", "updated_at": "test"}
        self.order[playlist_id] = []
        return self.get(name)

    def update(self, playlist_id, name, description):
        self._unique(name, playlist_id)
        self.playlists[playlist_id].update(name=name, description=description)

    def delete(self, playlist_id):
        self.playlists.pop(playlist_id, None)
        self.order.pop(playlist_id, None)

    def replace_tracks(self, playlist_id, track_ids):
        self.order[playlist_id] = list(track_ids)


class FakePublicURLRepository:
    """Provide an in-memory PublicURLRepository bound to the track rows."""

    def __init__(self, tracks: FakeTrackRepository) -> None:
        self.tracks = tracks
        self.base_url = ""

    def get(self):
        return self.base_url

    def seed(self, default_url):
        if not self.base_url:
            self.base_url = default_url
        if self.base_url:
            self._regenerate()
        return self.base_url

    def replace(self, public_base_url):
        self.base_url = public_base_url
        return self._regenerate()

    def _regenerate(self):
        for row in self.tracks.rows.values():
            row["public_url"] = f"{self.base_url}{PUBLIC_TRACK_PATH}{row['track_id']}"
        return len(self.tracks.rows)


class FakeCredentialRepository:
    """Provide an in-memory CredentialRepository test double."""

    def __init__(self):
        self.credentials = None

    def get(self):
        return self.credentials

    def create(self, credentials):
        if self.credentials is not None:
            return False
        self.credentials = credentials
        return True

    def update_password(self, salt, password_hash, iterations):
        self.credentials = type(self.credentials)(
            salt,
            password_hash,
            self.credentials.pin_salt,
            self.credentials.pin_hash,
            iterations,
        )


class FakeCaptioner:
    """Return a deterministic caption without calling Ollama, recording what it was given."""

    model = "test-caption"

    def __init__(self) -> None:
        self.calls = []

    def describe(self, facts, heard):
        self.calls.append((facts, heard))
        caption = f"{facts.title}: a calm piano piece." if facts.title else "A calm piano piece."
        return TrackDescription(caption=caption, tags=["piano", "calm"])


class FakeEncoder:
    """Stand in for CLAP: tracks embed by their dominant pitch, text by its words.

    Two tones of the same pitch embed identically (near-duplicates); different
    pitches embed differently. A text naming a pitch ("440 hz") embeds as that pitch.
    """

    model_name = "laion/fake-clap"
    DIMENSIONS = 8

    def __init__(self) -> None:
        self.texts = []

    @classmethod
    def for_pitch(cls, hertz: float) -> list[float]:
        angle = (hertz % 1000) / 1000 * np.pi
        vector = np.zeros(cls.DIMENSIONS)
        vector[0], vector[1] = np.cos(angle), np.sin(angle)
        return vector.round(6).tolist()

    def embed_audio(self, samples):
        window = samples[:48_000]
        hertz = float(np.argmax(np.abs(np.fft.rfft(window)))) * 48_000 / window.size
        return self.for_pitch(round(hertz / 10) * 10)

    def embed_text(self, text):
        self.texts.append(text)
        digits = "".join(character for character in text if character.isdigit())
        if digits:
            return self.for_pitch(float(digits))
        return self.for_pitch(int(hashlib.sha256(text.encode()).hexdigest(), 16) % 1000)

    def describe(self, embedding, per_group=3):
        return {"mood": ["calm"], "genre": ["piano solo"], "instrument": ["piano"], "setting": ["evening"],
                "voice": ["instrumental"]}


class FakeVisia(VisiaImageCatalog):
    """A Luna Visia catalog with fixed images, using the real URL rules."""

    VISIBLE_ID = "11111111-2222-3333-4444-555555555555"
    HIDDEN_ID = "99999999-8888-7777-6666-555555555555"
    FOOD_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def __init__(self, placeholder_image_id: str = "", store_error: Exception | None = None) -> None:
        super().__init__("http://visia.test", placeholder_image_id)
        self.stored: list[tuple[str, list[str], dict]] = []
        self.store_error = store_error
        self.tags: dict[str, list[str]] = {self.FOOD_ID: ["food", "luna vita"]}
        self.tag_calls: list[tuple[list[str], list[str]]] = []

    def tag(self, image_ids, tags):
        """Pretend Visia tagged the images."""
        self.tag_calls.append((image_ids, tags))
        for image_id in image_ids:
            current = self.tags.setdefault(image_id, [])
            current.extend(tag for tag in tags if tag not in current)
        return {"tagged_count": len(image_ids), "failed": []}

    def store(self, name, tags, source):
        """Pretend Visia stored the image as the visible one."""
        if self.store_error:
            raise self.store_error
        self.stored.append((name, tags, source))
        return {
            "status": "created", "name": f"{name}.png", "image_id": self.VISIBLE_ID,
            "public_url": f"https://visia.example.test/api/public/images/{self.VISIBLE_ID}",
        }

    def images(self):
        return [
            {"image_id": image_id, "hidden": hidden, "name": f"{image_id[:4]}.png",
             "tags": list(self.tags.get(image_id, [])),
             "public_url": f"https://visia.example.test/api/public/images/{image_id}"}
            for image_id, hidden in ((self.VISIBLE_ID, False), (self.HIDDEN_ID, True), (self.FOOD_ID, False))
        ]


class FakeSpeakerPlayer(SpeakerPlayer):
    """A host with fixed speakers that records each queue instead of playing it."""

    def __init__(self, speakers: list[Speaker]) -> None:
        super().__init__()
        self.connected = speakers
        self.played: list[tuple[list[tuple[str, Path]], Speaker, bool]] = []

    def speakers(self):
        return list(self.connected)

    def play(self, queue, speaker, loop):
        self.played.append((queue, speaker, loop))
        self._state = {"status": "playing", "speaker": speaker.as_row(), "tracks": [name for name, _ in queue],
                       "loop": loop, "now_playing": queue[0][0]}
        return self.status()

    def switch(self, speaker):
        queue, _, loop = self.played[-1]
        self.played.append((queue, speaker, loop))
        self._state = {**self._state, "speaker": speaker.as_row()}
        return self.status()


def tone(hertz=440.0, seconds=2.0, rate=48_000):
    t = np.arange(int(seconds * rate)) / rate
    return (0.4 * np.sin(2 * np.pi * hertz * t)).astype(np.float32)


def wav_bytes(hertz=440.0, seconds=2.0, rate=48_000):
    """A mono 16-bit WAV of a sine tone."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes((tone(hertz, seconds, rate) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def encoded(audio_format="mp3", hertz=440.0, seconds=2.0, **metadata):
    """The tone encoded by ffmpeg as ``audio_format``, with optional file tags."""
    command = ["ffmpeg", "-v", "error", "-f", "wav", "-i", "pipe:0"]
    for key, value in metadata.items():
        command += ["-metadata", f"{key}={value}"]
    muxer = {"m4a": "ipod", "ogg": "ogg"}.get(audio_format, audio_format)
    if audio_format == "m4a":
        command += ["-movflags", "frag_keyframe+empty_moov"]
    command += ["-f", muxer, "pipe:1"]
    return subprocess.run(command, input=wav_bytes(hertz, seconds), capture_output=True, check=True).stdout


def wav_payload(hertz=440.0, seconds=2.0):
    """Create a small valid Base64 WAV payload."""
    return base64.b64encode(wav_bytes(hertz, seconds)).decode("ascii")
