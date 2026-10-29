"""Music-text embeddings with CLAP: one space for how a track sounds and how it is described."""

from __future__ import annotations

import threading

import numpy as np

from app.core.config import AppConfig

# Words CLAP scores every track against; the best matches per group become hints for
# the caption model. Phrased as CLAP was trained: short descriptions of music.
VOCABULARY: dict[str, tuple[str, ...]] = {
    "mood": (
        "calm", "relaxing", "happy", "uplifting", "energetic", "melancholic", "sad",
        "romantic", "dreamy", "dark", "tense", "epic", "playful", "nostalgic", "peaceful",
    ),
    "genre": (
        "lo-fi hip hop", "jazz", "classical", "ambient", "acoustic folk", "pop", "rock",
        "electronic dance", "house", "techno", "hip hop", "r&b", "soul", "funk", "blues",
        "country", "indian classical", "bollywood", "cinematic orchestral", "metal",
        "reggae", "latin", "chillout", "synthwave", "piano solo",
    ),
    "instrument": (
        "piano", "acoustic guitar", "electric guitar", "bass", "drums", "strings",
        "violin", "synthesizer", "saxophone", "trumpet", "flute", "sitar", "tabla",
        "vocals", "choir", "pads",
    ),
    "setting": (
        "morning", "evening", "night", "coffee shop", "study", "focus", "workout",
        "party", "sleep", "rainy day", "road trip", "dinner", "meditation",
    ),
    "voice": ("instrumental", "male vocals", "female vocals"),
}


class ClapEncoder:
    """Embed audio and text into CLAP's shared space, on the CPU.

    The model loads on first use and stays loaded. A track is heard as up to
    ``CLAP_MAX_CLIPS`` 10-second clips spread over its length; their embeddings
    are averaged, so a long track is represented by its whole arc, not its intro.
    """

    def __init__(self, model_name: str = AppConfig.CLAP_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._processor = None
        self._lock = threading.Lock()
        self._vocabulary: dict[str, tuple[tuple[str, ...], np.ndarray]] | None = None

    def _load(self):
        with self._lock:
            if self._model is None:
                import torch
                from transformers import ClapModel, ClapProcessor

                torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
                self._processor = ClapProcessor.from_pretrained(self.model_name)
                self._model = ClapModel.from_pretrained(self.model_name).eval()
            return self._model, self._processor

    @staticmethod
    def clips(samples: np.ndarray) -> list[np.ndarray]:
        """Up to ``CLAP_MAX_CLIPS`` evenly spread 10-second clips of 48 kHz mono audio."""
        length = AppConfig.CLAP_SAMPLE_RATE * AppConfig.CLAP_CLIP_SECONDS
        if samples.size <= length:
            return [samples]
        count = min(AppConfig.CLAP_MAX_CLIPS, samples.size // length)
        starts = np.linspace(0, samples.size - length, count).astype(int)
        return [samples[start : start + length] for start in starts]

    @staticmethod
    def _features(output) -> np.ndarray:
        """The projected embeddings, whether a call returns a tensor or (Transformers 5) an output object."""
        tensor = output if hasattr(output, "numpy") else output.pooler_output
        return tensor.detach().numpy()

    @staticmethod
    def _unit(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def embed_audio(self, samples: np.ndarray) -> list[float]:
        """One unit-length embedding for a track, from 48 kHz mono samples."""
        import torch

        model, processor = self._load()
        with torch.no_grad():
            inputs = processor(audio=self.clips(samples), sampling_rate=AppConfig.CLAP_SAMPLE_RATE, return_tensors="pt")
            features = self._features(model.get_audio_features(**inputs))
        return self._unit(self._unit(features).mean(axis=0)).round(6).tolist()

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        import torch

        model, processor = self._load()
        with torch.no_grad():
            inputs = processor(text=texts, return_tensors="pt", padding=True)
            return self._unit(self._features(model.get_text_features(**inputs)))

    def embed_text(self, text: str) -> list[float]:
        """A unit-length embedding for a description such as "music for evening coffee"."""
        return self.embed_texts([text])[0].round(6).tolist()

    def describe(self, embedding: list[float], per_group: int = 3) -> dict[str, list[str]]:
        """The vocabulary words that best match a track, per group (mood, genre, ...)."""
        if self._vocabulary is None:
            self._vocabulary = {
                group: (words, self.embed_texts([f"{word} music" for word in words]))
                for group, words in VOCABULARY.items()
            }
        audio = np.asarray(embedding)
        matches = {}
        for group, (words, vectors) in self._vocabulary.items():
            scores = vectors @ audio
            best = np.argsort(scores)[::-1][: 1 if group == "voice" else per_group]
            matches[group] = [words[index] for index in best]
        return matches
