# Luna Vibia

![Docker required](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)
![Docker Compose v2](https://img.shields.io/badge/Docker_Compose-v2-2496ED?logo=docker&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Luna Sentia required](https://img.shields.io/badge/Luna_Sentia-required-111111?logo=ollama&logoColor=white)
![PostgreSQL in Luna Sentia](https://img.shields.io/badge/PostgreSQL-in_Luna_Sentia-4169E1?logo=postgresql&logoColor=white)
![Status: early](https://img.shields.io/badge/Status-early-D29922)

## Store, describe, and find music with LLMs

> **Work in progress:** Luna Vibia is a local-first music library under active development. A
> media player that plays Vibia's playlists on chosen speakers comes later.

Luna Vibia is the music counterpart of [Luna Visia](https://github.com/pranjallk1995/Luna_Visia)
(images) and [Luna Lexia](https://github.com/pranjallk1995/Luna_Lexia) (documents). An
assistant that generates music stores it here; every track is listened to, measured,
captioned, and tagged locally, and embedded so that a request such as "something for
evening coffee" finds the tracks that sound right, even when no stored word matches.
Cover art comes from Luna Visia.

## How a track is processed

```text
Upload (UI, MCP tool, upload link, or HTTP API)
  -> measure    ffprobe: format, duration, embedded tags; librosa: tempo, key, energy
  -> listen     CLAP (laion/clap-htsat-unfused, CPU): one embedding for the sound, plus
                the moods, genres, instruments, and settings it matches
  -> provenance tags naming an AI generator (Suno, Udio, Lyria, MusicGen, ...) -> "ai info"
  -> describe   Luna Sentia's model (Qwen3-VL, text only) writes a caption and tags from
                what CLAP heard, the measurements, and any title, artist, or generator notes
  -> store      the file in the track volume; metadata and the embedding in PostgreSQL
```

The steps run as a LangGraph graph (`mcp/app/services/analysis_graph.py`): listen and
the provenance check run in parallel after measuring. The caption model never hears
the audio; it turns the evidence into words, and is told to keep only matches that
agree with each other and the measurements.

- **CLAP** maps music and text into one 512-dimensional space. A track is heard as up
  to six 10-second clips spread over its length, whose embeddings are averaged. It
  runs on the CPU inside the MCP container (about 1 GB of RAM), so it does not compete
  with Luna Sentia's model for the GPU; the weights are baked into the image.
- **Generator notes** are the strongest signal: when an assistant generated the music,
  it should pass the prompt or style it used as `notes` with the upload. They are stored
  and used for the caption.

## Search and playlists

Search embeds the request with CLAP's text side and ranks every visible track by its
cosine similarity to the sound, blended with the full-text rank of its name, caption,
title, artist, and tags (75% meaning, 25% words; `SEMANTIC_WEIGHT` in
`mcp/app/core/config.py`). Tags and minimum or maximum length narrow the results.

`suggest_playlist` turns a mood into a looping playlist: it takes the 60 best matches,
drops those well below the best one, then picks tracks one at a time by how well they
fit minus how much they sound like the tracks already picked, until the requested
length is filled. With too little fitting music it returns a shorter playlist and says
to loop it.

## Cover art from Luna Visia

A track's cover is an image stored in Luna Visia. `set_track_cover` (or **Cover art**
in a track's dialog) accepts only Visia's immutable image-ID URLs
(`.../api/public/images/<image-id>`), checks that the image exists and is visible in
Visia, and stores Visia's canonical public URL. The UI fetches covers from Visia over
`luna_sentia_network`; tracks without one show a generated placeholder. Visia must be
running for covers to be set or shown.

## Start

Start [Luna Sentia](https://github.com/pranjallk1995/Luna_Sentia) first and wait until it
is healthy. Sentia's PostgreSQL holds Vibia's `lunavibia` database (with pgvector) and its
Ollama serves the caption model.

```sh
cd ../Luna_Sentia
docker compose up -d --wait postgres ollama adminer
docker compose run --rm postgres-init   # creates the lunavibia role and database
```

`LUNAVIBIA_DB_PASSWORD` in Sentia's `.env` must equal `POSTGRES_PASSWORD` in Vibia's.
To start Sentia and every Luna app together, use `../luna.sh start`; see the
[Sentia README](https://github.com/pranjallk1995/Luna_Sentia#start-everything).

Create a private `.env` from `.env.example`:

```dotenv
POSTGRES_PASSWORD=replace-with-a-private-database-password
CAPTION_MODEL=qwen3-vl:8b-instruct
LUNAVISIA_API_URL=http://luna-visia-mcp:8000
LUNAVIBIA_PUBLIC_BASE_URL=https://vibia.example.com
LUNAVIBIA_API_TOKEN=replace-with-a-random-value-of-at-least-32-characters
LUNAVIBIA_ALLOWED_EMAILS=you@example.com
MCP_PUBLIC_URL=https://vibia-mcp.example.com
LUNA_SSO_URL=https://auth.example.com
LUNA_SSO_INTERNAL_URL=http://luna-sentia-auth:8000
```

- `LUNAVIBIA_API_TOKEN` is a shared secret between the UI and the MCP server; generate
  one with `openssl rand -hex 32`.
- `LUNAVIBIA_PUBLIC_BASE_URL` is the HTTPS origin of playable track URLs
  (`.../api/public/tracks/<track-id>`); route it to `127.0.0.1:18005`.
- Sign-in goes through Luna Sentia's single sign-on, as in every Luna app; see
  [Single sign-on](https://github.com/pranjallk1995/Luna_Sentia#single-sign-on).

```sh
docker compose up -d
```

- UI: <http://127.0.0.1:18506>
- Service health: <http://127.0.0.1:18005/health>
- MCP endpoint: <http://127.0.0.1:18005/mcp>

## MCP tools

### Find and play

- `search_tracks` - rank tracks for a description ("upbeat electronic for a run"), with optional tags and length limits.
- `suggest_playlist` - a looping playlist for a mood or moment, about `minutes` long, without near-duplicates.
- `list_tracks` - visible tracks newest first, with captions, facts, `cover_url`, and playable `public_url`.
- `get_track_url` - the playable public URL of one track.

### Add and change

- `upload_track` - add MP3, WAV, FLAC, OGG/Opus, or M4A from a chat attachment (`file`), `track_url`, or `content_base64`, with optional `title`, `artist`, and generator `notes`. Names are corrected and deduplicated like Visia's.
- `create_upload_link` - a single-use HTTPS link to POST a local file to (up to 200 MiB).
- `modify_track` - replace a track's audio; title, artist, notes, and cover are kept.
- `set_track_cover` - set or clear the cover to a Luna Visia image.
- `update_track_metadata` / `update_tracks_metadata` - edit captions and tags.
- `rename_track` / `rename_tracks`, `set_favorite_tracks`, `remove_track`.

### Metadata and library

- `get_track_metadata` / `list_track_metadata` - stored, measured, and embedded details, including AI-generator signals.
- `get_library_stats` - counts, listening time, formats, covers, and top tags.
- `download_tracks` - a 24-hour ZIP link to the original files.
- `backfill_metadata` - analyze files missing current metadata.
- `set_public_base_url` - change the public origin and regenerate every track URL.

## Data model

`track_metadata` holds one row per track: name, immutable `track_id`, size and SHA-256,
caption and tags, title, artist, generator notes, format, duration, sample rate,
channels, bitrate, tempo, key, energy, `cover_url`, the CLAP `embedding` (pgvector, HNSW
cosine index), a weighted full-text `search_vector`, and the hidden, favorite, and
public-URL fields. `vault_security` and `vault_config` are as in Luna Visia.

## Database UI

Use [Adminer in Luna Sentia](https://github.com/pranjallk1995/Luna_Sentia#database-ui) at
<http://127.0.0.1:19080>: server `luna-sentia-db`, username and database `lunavibia`,
password your `POSTGRES_PASSWORD`.

## Development workflow

```sh
docker compose up -d --build
docker compose exec mcp python -m unittest discover -s tests
```

Tests use fake CLAP and caption models and real ffmpeg, so they run in the MCP image
without the model weights being loaded.
