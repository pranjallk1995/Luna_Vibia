"""Score old.jsonl against new.jsonl: how well captions match each track's sound, invented tags, time.

usage: python score.py <dir with old.jsonl and new.jsonl> [--user u_owner]
Runs inside the MCP container (it needs CLAP and the stored audio embeddings). Writes
scores.json and report.md to the same directory.

- caption_match: CLAP's cosine similarity between the caption and the track's stored
  audio embedding, the same space search by description uses.
- tags_grounded: the share of tags with a word found in the evidence the model was given
  (CLAP's matches, the measurements, title, artist, notes). The prompt asks it to keep to
  that evidence, so a low share means invented tags. Tempo words ("slow", "upbeat") are
  counted as grounded when a tempo was measured.
"""

import argparse
import json
import re
from pathlib import Path
from statistics import mean, median

import numpy as np
import psycopg

from app.core.config import AppConfig
from app.integrations.clap import ClapEncoder

parser = argparse.ArgumentParser()
parser.add_argument("dir", type=Path)
parser.add_argument("--user", default="u_owner")
args = parser.parse_args()

TEMPO_WORDS = {"slow", "fast", "upbeat", "midtempo", "mid", "tempo", "downtempo", "uptempo", "moderate"}
WORD = re.compile(r"[a-z0-9]+")


def load(path: Path) -> dict:
    return {r["name"]: r for r in map(json.loads, path.read_text().splitlines()) if r}


def words(text: str) -> set[str]:
    found = set(WORD.findall(text.lower()))
    return found | {w[:-1] for w in found if w.endswith("s")}


def grounded_share(tags: list[str], evidence: dict) -> float:
    known = words(json.dumps(evidence))
    if evidence.get("measured", {}).get("tempo_bpm"):
        known |= TEMPO_WORDS
    hits = [bool(words(tag) & known) for tag in tags]
    return round(sum(hits) / len(hits), 3) if hits else 0.0


runs = {label: load(args.dir / f"{label}.jsonl") for label in ("old", "new")}
names = sorted(set(runs["old"]) & set(runs["new"]))
with psycopg.connect(AppConfig.from_env().database_url) as conn:
    stored = {
        name: np.asarray(json.loads(vector), dtype=np.float32)
        for name, vector in conn.execute(
            f"SELECT name, embedding::text FROM {args.user}.track_metadata WHERE name = ANY(%s)", (names,)
        ).fetchall()
    }
clap = ClapEncoder(device=AppConfig.from_env().clap_device)

per_track = []
for name in names:
    entry = {"name": name, "evidence": runs["new"][name]["evidence"]}
    for label in ("old", "new"):
        row = runs[label][name]
        if "crash" in row:
            entry[label] = {"crash": row["crash"], "seconds": row["seconds"]}
            continue
        entry[label] = {
            "caption": row["caption"],
            "tags": row["tags"],
            "caption_match": round(float(np.dot(clap.embed_text(row["caption"]), stored[name])), 4),
            "tags_grounded": grounded_share(row["tags"], row["evidence"]),
            "tag_count": len(row["tags"]),
            "caption_chars": len(row["caption"]),
            "seconds": row["seconds"],
        }
    per_track.append(entry)


def summarize(label: str) -> dict:
    scores = [e[label] for e in per_track]
    ok = [s for s in scores if "crash" not in s]
    pick = lambda key: round(mean(s[key] for s in ok), 4) if ok else None  # noqa: E731
    return {
        "tracks": len(scores),
        "failures": len(scores) - len(ok),
        "caption_match_mean": pick("caption_match"),
        "tags_grounded_mean": pick("tags_grounded"),
        "tag_count_mean": pick("tag_count"),
        "caption_chars_median": median(s["caption_chars"] for s in ok) if ok else None,
        "mean_seconds": round(mean(s["seconds"] for s in scores), 1),
        "total_minutes": round(sum(s["seconds"] for s in scores) / 60, 1),
    }


both = [e for e in per_track if "crash" not in e["old"] and "crash" not in e["new"]]
for e in both:
    e["caption_gain"] = round(e["new"]["caption_match"] - e["old"]["caption_match"], 4)
summary = {
    "old": {"model": next(iter(runs["old"].values()))["model"], **summarize("old")},
    "new": {"model": next(iter(runs["new"].values()))["model"], **summarize("new")},
    "new_caption_better": sum(e["caption_gain"] > 0.01 for e in both),
    "new_caption_worse": sum(e["caption_gain"] < -0.01 for e in both),
}
(args.dir / "scores.json").write_text(json.dumps({"summary": summary, "per_track": per_track}, indent=1, default=str))

lines = ["# Vibia caption evaluation", "", "```json", json.dumps(summary, indent=1), "```", ""]
for title, chosen in (
    ("Biggest drops (check these by hand)", sorted(both, key=lambda e: e["caption_gain"])[:10]),
    ("Biggest gains", sorted(both, key=lambda e: -e["caption_gain"])[:5]),
    ("Failures", [e for e in per_track if "crash" in e["old"] or "crash" in e["new"]][:10]),
):
    lines += [f"## {title}", ""]
    for e in chosen:
        lines.append(f"### {e['name']} ({e.get('caption_gain', 'failed')})")
        lines.append(f"- heard: {json.dumps(e['evidence'].get('audio_model_matches'))}")
        for label in ("old", "new"):
            s = e[label]
            text = s.get("crash") or (f"{s['caption']} [{', '.join(s['tags'])}] "
                                      f"(match {s['caption_match']}, grounded {s['tags_grounded']})")
            lines.append(f"- {label}: {text}")
        lines.append("")
(args.dir / "report.md").write_text("\n".join(lines))
print(json.dumps(summary, indent=1))
