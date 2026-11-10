# Model evaluations

Compare two caption models on every stored track before changing `CAPTION_MODEL`. The
caption model does not hear the audio: it writes from the evidence CLAP and the
measurements give it. `run.py` rebuilds that evidence for each track from what is stored
(its tempo, key, energy, title, artist and notes, and what CLAP hears in its stored
embedding), so both models get exactly the same input, through Vibia's own prompt,
schema and settings. Nothing is written to the database. Results are kept out of git in
`results/` (see `.gitignore`).

## What is scored

| Measure | What it shows |
| --- | --- |
| `failures` | Replies that broke the schema, had no usable tags, or timed out |
| `caption_match_mean` | CLAP's cosine similarity between each caption and the track's stored audio embedding: the space search by description uses |
| `tags_grounded_mean` | The share of tags with a word found in the evidence; the prompt asks the model to keep to it, so a lower share means invented tags |
| `new_caption_better` / `new_caption_worse` | Tracks where the new caption scores more than 0.01 higher or lower |
| `tag_count_mean`, `caption_chars_median` | Whether captions got longer or tags fewer |
| `mean_seconds`, `total_minutes` | Speed, including model loads |

Read the biggest drops in `report.md`, with what CLAP heard beside each caption, before
deciding: a caption can score well and still claim vocals the track does not have.

## Running one

```sh
C=luna_vibia-mcp-1
docker exec $C mkdir -p /tmp/vibia_eval
docker cp model_evaluations/run.py $C:/tmp/vibia_eval/
docker cp model_evaluations/score.py $C:/tmp/vibia_eval/
docker exec -e PYTHONPATH=/workspace/mcp $C python /tmp/vibia_eval/run.py old qwen3-vl:8b-instruct /tmp/vibia_eval/old.jsonl
docker exec -e PYTHONPATH=/workspace/mcp $C python /tmp/vibia_eval/run.py new <model> /tmp/vibia_eval/new.jsonl
docker exec -e PYTHONPATH=/workspace/mcp $C python /tmp/vibia_eval/score.py /tmp/vibia_eval
docker cp $C:/tmp/vibia_eval model_evaluations/results/<date>_<old>-vs-<new>
```

`run.py` takes every track that has an embedding, in content-hash order; `--limit N`
keeps a trial run to the first N, and `--user` picks another person's library (default
`u_owner`). A run that stops resumes where it left off.

Run Luna Sentia's `model_checks/check_model.py` on the new model first: it checks JSON
output, `think: false` and the GPU fit in a minute.
