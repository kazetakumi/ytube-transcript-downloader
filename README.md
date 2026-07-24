# yttdl

Download YouTube captions as plain text — single videos, playlists, or whole
channels — usable as a CLI **and** a Python library. Built with an anti-ban
proxy layer so it can scale.

## How it works

- **`yt-dlp`** expands any URL (video / playlist / channel / bare ID) into video IDs.
- **`youtube-transcript-api`** fetches each video's captions — manually-created
  preferred, auto-generated as fallback.
- **Proxies** (BYO generic or Webshare residential) + retry/backoff + an
  on-disk cache keep you from getting IP-blocked.

## CLI

```bash
uv run yttdl "https://www.youtube.com/watch?v=VIDEO_ID"
uv run yttdl "https://www.youtube.com/playlist?list=..." -o transcripts --cache .cache
uv run yttdl VIDEO_ID_1 VIDEO_ID_2 -l en,de          # language priority
```

One `<video_id>.txt` is written per video. Videos with captions disabled are
skipped and reported; the batch never aborts on a single failure.

## Library

```python
from yttdl import fetch_transcript, download_transcripts, ProxySettings

text = fetch_transcript("VIDEO_ID", languages=("en",), cache_dir=".cache")

results = download_transcripts(
    ["https://www.youtube.com/playlist?list=..."],
    out_dir="transcripts",
    proxy=ProxySettings(webshare_username="...", webshare_password="..."),
)
for r in results:
    print(r.video_id, "ok" if r.ok else r.error)
```

## Proxies (anti-ban)

YouTube blocks datacenter IPs aggressively. Configure a proxy via env or code:

| Env var | Meaning |
| --- | --- |
| `YTTDL_PROXY_HTTP` / `YTTDL_PROXY_HTTPS` | Generic BYO proxy URL |
| `YTTDL_WEBSHARE_USER` / `YTTDL_WEBSHARE_PASS` | Webshare residential pool |

Webshare takes precedence when both are set. Without a proxy it works fine for
light/personal use — proxies matter once you fetch at volume.

## Scope & the commercial path

This is the **core**, built to be wrapped later. Deliberately *not* included yet
(decide when you pick a business model): the hosted API / SaaS layer, auth,
billing, and the official-YouTube-Data-API vs. scraping decision.

> ⚠️ Personal transcript downloading is routine. Commercially reselling scraped
> transcripts runs against YouTube's Terms of Service, and residential-proxy
> scraping is legally gray — validate this before building the commercial layer.
> Many commercial products route through the official YouTube Data API instead.
