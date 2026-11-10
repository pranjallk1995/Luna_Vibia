"""Caption and tag every stored track with one model; write JSONL, never touch the database.

usage: python run.py <label: old|new> <model> <out.jsonl> [--limit N]
Runs inside the MCP container with the app's code on PYTHONPATH (/workspace/mcp). Each
track's evidence is rebuilt from what is stored: its facts (tempo, key, energy, title,
artist, notes) and what CLAP hears in its stored embedding. Both labels use the app's
own prompt and settings; only the caption model differs. A run that stops resumes.
"""

import argparse
import dataclasses
import json
import time
import traceback
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.config import AppConfig
from app.core.models import AudioFacts, MetadataRules
from app.integrations.captioning import OllamaCaptioner
from app.integrations.clap import ClapEncoder

parser = argparse.ArgumentParser()
parser.add_argument("label", choices=["old", "new"])
parser.add_argument("model")
parser.add_argument("out", type=Path)
parser.add_argument("--limit", type=int, default=0, help="only the first N tracks (by content hash)")
parser.add_argument("--user", default="u_owner", help="whose library: the schema name")
args = parser.parse_args()

config = AppConfig.from_env()
captioner = OllamaCaptioner(config.ollama_url, args.model, MetadataRules(config.max_tags, config.search_stop_words))
fields = [field.name for field in dataclasses.fields(AudioFacts)]
with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
    rows = conn.execute(
        f"SELECT name, embedding::text AS embedding, {', '.join(fields)} FROM {args.user}.track_metadata "
        "WHERE embedding IS NOT NULL ORDER BY content_sha256"
    ).fetchall()
if args.limit:
    rows = rows[: args.limit]

done = set()
if args.out.exists():
    done = {json.loads(line)["name"] for line in args.out.read_text().splitlines() if line.strip()}

clap = ClapEncoder(device=config.clap_device)
with args.out.open("a") as out:
    for i, track in enumerate(rows, 1):
        if track["name"] in done:
            continue
        facts = AudioFacts(**{field: track[field] for field in fields})
        heard = clap.describe(json.loads(track["embedding"]))
        started = time.monotonic()
        row = {"name": track["name"], "label": args.label, "model": args.model,
               "evidence": json.loads(captioner.evidence(facts, heard))}
        try:
            description = captioner.describe(facts, heard)
            row.update(caption=description.caption, tags=description.tags)
        except Exception as error:  # noqa: BLE001 - a failure is a result
            row.update(crash=f"{type(error).__name__}: {error}"[:500], trace=traceback.format_exc()[-1500:])
        row["seconds"] = round(time.monotonic() - started, 1)
        out.write(json.dumps(row, default=str) + "\n")
        out.flush()
        print(f"[{args.label}] {i}/{len(rows)} {track['name']} {row['seconds']}s", flush=True)
