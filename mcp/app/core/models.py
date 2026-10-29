"""Validated metadata models and normalization rules for Luna Vibia."""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class TrackDescription(BaseModel):
    """Validated caption and tag payload returned by the caption model."""

    caption: str = Field(min_length=3, max_length=500)
    tags: list[str] = Field(min_length=1, max_length=16)


@dataclass(frozen=True)
class AudioFacts:
    """What a track's file says about it and what can be measured from its sound."""

    audio_format: str
    duration_seconds: float
    sample_rate: int | None = None
    channels: int | None = None
    bitrate: int | None = None
    title: str | None = None
    artist: str | None = None
    # A generator prompt or note: given at upload, or found in the file's tags.
    notes: str | None = None
    tempo_bpm: float | None = None
    musical_key: str | None = None
    # Mean loudness of the sound on a 0-1 scale, for "calm" versus "energetic".
    energy: float | None = None


@dataclass(frozen=True)
class TrackAnalysis:
    """Everything analysis produces for one track: description, facts, and embedding."""

    caption: str
    tags: list[str]
    facts: AudioFacts
    # The CLAP audio embedding, in the space CLAP's text embeddings share.
    embedding: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class TrackRecord:
    """Content identity, generated metadata, and audio facts for one stored track."""

    name: str
    size_bytes: int
    content_sha256: str
    caption: str
    tags: list[str]
    analysis_model: str
    facts: AudioFacts
    embedding: list[float]


@dataclass(frozen=True)
class MetadataChange:
    """An explicit caption edit and/or tag additions and removals."""

    caption: str | None = None
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None

    @property
    def is_empty(self) -> bool:
        return self.caption is None and self.add_tags is None and self.remove_tags is None


class MetadataRules:
    """Normalize captions, tags, and search text consistently across use cases."""

    CAPTION_MIN_LENGTH = 3
    CAPTION_MAX_LENGTH = 500
    TAG_MAX_LENGTH = 60

    def __init__(self, max_tags: int, search_stop_words: frozenset[str]) -> None:
        self.max_tags = max_tags
        self.search_stop_words = search_stop_words

    @staticmethod
    def require_lowercase_tags(tags: list[str] | None, field: str) -> list[str] | None:
        """Reject tags containing capital letters instead of silently lowercasing them."""
        capitalized = [tag for tag in tags or [] if tag != tag.lower()]
        if capitalized:
            suggestions = ", ".join(repr(tag.lower()) for tag in capitalized)
            raise ValueError(
                f"{field} must be lowercase; capital letters are not allowed in tags. "
                f"Use {suggestions} instead."
            )
        return tags

    def normalize_tags(self, tags: list[str]) -> list[str]:
        """Normalize, deduplicate, and bound search tags."""
        normalized = []
        for tag in tags:
            clean = re.sub(r"[^a-z0-9 -]+", "", tag.lower()).strip()
            clean = re.sub(r"\s+", " ", clean)
            if clean and clean not in normalized:
                normalized.append(clean[: self.TAG_MAX_LENGTH])
        if not normalized:
            raise ValueError("Analysis returned no usable tags.")
        return normalized[: self.max_tags]

    def caption(self, value: str) -> str:
        """Return a trimmed caption that satisfies the length policy."""
        caption = value.strip()
        if not self.CAPTION_MIN_LENGTH <= len(caption) <= self.CAPTION_MAX_LENGTH:
            raise ValueError("Caption must contain between 3 and 500 characters.")
        return caption

    def edited_tags(
        self,
        current: list[str],
        add_tags: list[str] | None,
        remove_tags: list[str] | None,
    ) -> list[str]:
        """Apply tag removals then additions while keeping order and bounds."""
        additions = self.normalize_tags(add_tags) if add_tags else []
        removals = set(self.normalize_tags(remove_tags)) if remove_tags else set()
        updated = [tag for tag in current if tag not in removals]
        for tag in additions:
            if tag not in updated:
                updated.append(tag)
        if not updated:
            raise ValueError("At least one tag must remain on the track.")
        if len(updated) > self.max_tags:
            raise ValueError(f"Tracks can have at most {self.max_tags} tags.")
        return updated

    def with_tags(self, tags: list[str], extra: list[str]) -> list[str]:
        """Append system tags, dropping trailing other tags to stay within the limit."""
        extra = [tag for tag in extra if tag not in tags]
        return [*tags[: max(self.max_tags - len(extra), 0)], *extra]

    def search_query(self, query: str) -> str:
        """Reduce natural-language search text to meaningful indexed words."""
        words = re.findall(r"[a-z0-9]+", query.lower())
        return " ".join(word for word in words if word not in self.search_stop_words)
