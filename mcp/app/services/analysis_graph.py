"""Track analysis as a LangGraph state graph.

                ┌─▶ listen ────────────┐
    START ─▶ measure                   ├─▶ describe ─▶ tag ─▶ END
                └─▶ check_provenance ─┘

measure reads the file (format, duration, embedded tags) and measures tempo, key,
and energy. listen embeds the sound with CLAP and finds the moods, genres,
instruments, and settings it matches; check_provenance looks for AI-generator
signals in the tags. Both depend only on measure, so they run in parallel.
describe has the caption model turn all of it into a caption and tags, and tag
adds the "ai modified" and "ai info" system tags.
"""

from __future__ import annotations

from typing import TypedDict

import numpy as np
from langgraph.graph import END, START, StateGraph

from app.core.config import AppConfig
from app.core.models import AudioFacts, MetadataRules, TrackAnalysis, TrackDescription
from app.integrations.audio import AudioProbe, MusicFeatures
from app.integrations.captioning import OllamaCaptioner
from app.integrations.clap import ClapEncoder
from app.services.inspection import TrackInspector


class TrackAnalysisState(TypedDict, total=False):
    """One track's bytes and what each step learned about them."""

    data: bytes
    modified: bool
    # Title, artist, or generator notes supplied with the upload; they win over file tags.
    given: dict[str, str]
    facts: AudioFacts
    samples: np.ndarray
    embedding: list[float]
    heard: dict[str, list[str]]
    ai_generated: bool
    description: TrackDescription
    analysis: TrackAnalysis


class TrackAnalysisGraph:
    """Measure a track, listen to it and check its provenance in parallel, then describe it."""

    AI_MODIFIED_TAG = "ai modified"
    # Marks tracks whose embedded tags name an AI music generator.
    AI_INFO_TAG = "ai info"

    def __init__(
        self,
        captioner: OllamaCaptioner,
        encoder: ClapEncoder,
        inspector: TrackInspector,
        rules: MetadataRules,
        probe: AudioProbe | None = None,
        features: MusicFeatures | None = None,
    ) -> None:
        self.captioner = captioner
        self.encoder = encoder
        self.inspector = inspector
        self.rules = rules
        self.probe = probe or AudioProbe()
        self.features = features or MusicFeatures()
        graph = StateGraph(TrackAnalysisState)
        graph.add_node("measure", self.measure)
        graph.add_node("listen", self.listen)
        graph.add_node("check_provenance", self.check_provenance)
        graph.add_node("describe", self.describe)
        graph.add_node("tag", self.tag)
        graph.add_edge(START, "measure")
        graph.add_edge("measure", "listen")
        graph.add_edge("measure", "check_provenance")
        graph.add_edge(["listen", "check_provenance"], "describe")
        graph.add_edge("describe", "tag")
        graph.add_edge("tag", END)
        self.graph = graph.compile(name="vibia-track-analysis")

    def run(self, data: bytes, modified: bool = False, given: dict[str, str] | None = None) -> TrackAnalysis:
        """Analyze bytes, tagging replacements and AI-generated tracks."""
        state = {"data": data, "modified": modified, "given": {k: v for k, v in (given or {}).items() if v}}
        return self.graph.invoke(state)["analysis"]

    def measure(self, state: TrackAnalysisState) -> TrackAnalysisState:
        probed = self.probe.probe(state["data"])
        samples = self.probe.decode(state["data"], AppConfig.CLAP_SAMPLE_RATE)
        excerpt = MusicFeatures.middle(samples, AppConfig.CLAP_SAMPLE_RATE, AppConfig.FEATURE_MAX_SECONDS)
        # The track is decoded once, at CLAP's 48 kHz; librosa's beat and key analysis is
        # tuned for 22.05 kHz, so only the short excerpt it measures is resampled.
        import librosa

        measured = self.features.measure(
            librosa.resample(excerpt, orig_sr=AppConfig.CLAP_SAMPLE_RATE, target_sr=AppConfig.FEATURE_SAMPLE_RATE),
            AppConfig.FEATURE_SAMPLE_RATE,
        )
        tags, given = probed["tags"], state["given"]
        facts = AudioFacts(
            audio_format=probed["format"],
            duration_seconds=probed["duration_seconds"] or round(samples.size / AppConfig.CLAP_SAMPLE_RATE, 2),
            sample_rate=probed["sample_rate"],
            channels=probed["channels"],
            bitrate=probed["bitrate"],
            title=given.get("title") or tags.get("title"),
            artist=given.get("artist") or tags.get("artist"),
            notes=given.get("notes") or tags.get("description") or tags.get("comment"),
            **measured,
        )
        return {"facts": facts, "samples": samples}

    def listen(self, state: TrackAnalysisState) -> TrackAnalysisState:
        embedding = self.encoder.embed_audio(state["samples"])
        return {"embedding": embedding, "heard": self.encoder.describe(embedding)}

    def check_provenance(self, state: TrackAnalysisState) -> TrackAnalysisState:
        return {"ai_generated": self.inspector.is_ai_generated(state["data"])}

    def describe(self, state: TrackAnalysisState) -> TrackAnalysisState:
        return {"description": self.captioner.describe(state["facts"], state["heard"])}

    def tag(self, state: TrackAnalysisState) -> TrackAnalysisState:
        description = state["description"]
        extra = [self.AI_MODIFIED_TAG] if state["modified"] else []
        if state["ai_generated"]:
            extra.append(self.AI_INFO_TAG)
        tags = self.rules.with_tags(description.tags, extra) if extra else description.tags
        return {
            "analysis": TrackAnalysis(
                caption=description.caption, tags=tags, facts=state["facts"], embedding=state["embedding"]
            )
        }
