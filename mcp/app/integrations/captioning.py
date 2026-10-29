"""Caption and tag tracks with Luna Sentia's model, from what was heard and measured."""

from __future__ import annotations

import json

import httpx

from app.core.config import AppConfig
from app.core.models import AudioFacts, MetadataRules, TrackDescription


class OllamaCaptioner:
    """Write a track's caption and tags with a local Ollama model.

    The model does not hear the audio. It is given what CLAP heard (the moods,
    genres, instruments, and settings that best match the sound), the measured
    tempo, key, and energy, and any title, artist, or generator prompt, and turns
    them into a caption and searchable tags.
    """

    PROMPT = (
        "Describe one music track for a searchable library, using only the evidence below. "
        "Return a concise factual caption (one or two sentences: style, mood, instruments, "
        "tempo feel, and what it suits) and 5-12 lowercase searchable tags covering genre, "
        "mood, instruments, setting, and tempo, in English. The generator notes, title, and "
        "artist come from whoever made the track: where they name an instrument, style, or "
        "mood, trust them over the audio-model matches. The audio-model matches are "
        "likelihoods from a fixed vocabulary, not certainties: keep only the ones that agree "
        "with each other, the notes, and the measurements, and mention vocals only when "
        "something besides that guess supports them. Never invent lyrics, artists, or "
        "titles.\n\nEVIDENCE:\n{evidence}"
    )

    def __init__(self, base_url: str, model: str, rules: MetadataRules) -> None:
        self.base_url = base_url
        self.model = model
        self.rules = rules

    @staticmethod
    def evidence(facts: AudioFacts, heard: dict[str, list[str]]) -> str:
        measured = {
            "duration_seconds": facts.duration_seconds,
            "tempo_bpm": facts.tempo_bpm,
            "key": facts.musical_key,
            "energy_0_to_1": facts.energy,
        }
        given = {"title": facts.title, "artist": facts.artist, "generator_notes": facts.notes}
        return json.dumps(
            {
                "audio_model_matches": heard,
                "measured": {key: value for key, value in measured.items() if value is not None},
                "from_file_or_uploader": {key: value for key, value in given.items() if value},
            },
            indent=1,
        )

    def describe(self, facts: AudioFacts, heard: dict[str, list[str]]) -> TrackDescription:
        payload = {
            "model": self.model,
            "stream": False,
            "format": TrackDescription.model_json_schema(),
            # Thinking models (Qwen3-VL) otherwise reason at length before every reply.
            "think": False,
            "options": {"temperature": 0, "num_ctx": AppConfig.CAPTION_CONTEXT_TOKENS},
            "messages": [{"role": "user", "content": self.PROMPT.format(evidence=self.evidence(facts, heard))}],
        }
        timeout = httpx.Timeout(AppConfig.CAPTION_TIMEOUT_SECONDS, connect=AppConfig.CAPTION_CONNECT_TIMEOUT_SECONDS)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
        description = TrackDescription.model_validate_json(response.json()["message"]["content"])
        description.caption = description.caption.strip()
        description.tags = self.rules.normalize_tags(description.tags)
        return description
