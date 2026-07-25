---
name: yttdl
description: Download YouTube captions as plain text files — single videos, playlists, whole channels, or batches from a file. Use when the user wants transcript(s) saved to disk, especially many videos at once. Not for watching/analyzing one video's content or frames — use the `watch` skill for that.
---

# yttdl

## Resolve `SKILL_DIR` first

Set `SKILL_DIR` to the absolute path of the directory containing **this**
SKILL.md (your harness told you that path when it loaded the skill). Every
command below runs from there via `uv run --project`, so it works regardless
of the caller's install location.

```bash
uv run --project "$SKILL_DIR" yttdl --help
```

Requires `uv` (https://docs.astral.sh/uv/). First invocation syncs the venv
from `uv.lock` — needs network, takes a few seconds, silent after that.

## Quick start

`-o` is relative to **the caller's current directory**, not `$SKILL_DIR` —
always pass it explicitly so files land where the user expects, e.g. next to
their own project instead of inside the skill's own folder.

```bash
uv run --project "$SKILL_DIR" yttdl "<video-or-playlist-or-channel-url>" -o transcripts
```

One `<video_id>.txt` is written per video into `-o`. Batches fetch one video
at a time (gentle on YouTube); a single failure doesn't abort the run.

## Non-English videos — default to `--translate`

Default language is `-l en`. If a video's captions aren't in that language
(e.g. a Spanish video is tagged `es`, not `en`), it's reported as **failed** —
`-l` does not translate, only prioritizes. Unless the user asks for original-
language output, prefer:

```bash
uv run --project "$SKILL_DIR" yttdl "<url>" -o transcripts --translate en
```

This gets English out of almost any captioned video (falls back to the
original language if translation to the target isn't offered).

## Batches

```bash
uv run --project "$SKILL_DIR" yttdl -f urls.txt -o transcripts --report run.json
```

`urls.txt`: one URL/ID per line, `#` comments allowed. Re-running skips
videos already saved in `-o` (pass `--overwrite` to force). `--report`
writes a JSON manifest — check it after a large run for per-video failures.

## Full reference

All flags (proxies, proxy pool, retries, caching, language priority lists)
are documented in `$SKILL_DIR/README.md` — read it before reaching for a flag
not shown above.
