# yttdl

Download YouTube captions as plain text — single videos, playlists, or whole
channels — usable as a CLI **and** a Python library. Built with an anti-ban
proxy layer so it can scale.

## How it works

- **`yt-dlp`** expands any URL (video / playlist / channel / bare ID) into video IDs.
- **Two caption backends**, tried in order:
  1. **yt-dlp** (default) — pulls captions via YouTube's player API with a real
     browser TLS fingerprint (`curl_cffi` impersonation). Far more resistant to
     IP blocks; works from a plain IP without a proxy.
  2. **youtube-transcript-api** (fallback) — scrapes the `timedtext` endpoint;
     used only when yt-dlp can't get a video.
- **Anti-ban:** browser impersonation + optional proxies (BYO generic or
  Webshare residential) + retry/backoff + an on-disk cache (never re-fetch).

## CLI

```bash
uv run yttdl "https://www.youtube.com/watch?v=VIDEO_ID"
uv run yttdl "https://www.youtube.com/playlist?list=..." -o transcripts --cache .cache
uv run yttdl VIDEO_ID_1 VIDEO_ID_2 -l en,de          # language priority
uv run yttdl -f urls.txt --report run.json           # batch from a file + manifest
```

One `<video_id>.txt` is written per video. Videos are fetched **one at a time**
to stay gentle on YouTube and avoid IP blocks. Videos with captions disabled are
skipped and reported; the batch never aborts on a single failure.

**Non-English videos:** `-l` is a priority list, tried in order (`-l es,en`).
By default, if none of your languages exist for a video it's reported as failed
(a Spanish-spoken video's auto-captions are tagged `es`, not `en`). Two opt-in
flags handle foreign videos:

- `--fallback-any` — if none of `-l` match, save whatever transcript the video
  has, in its original language.
- `--translate LANG` — machine-translate (via YouTube) to `LANG` when the chosen
  transcript isn't already in it; implies `--fallback-any`. E.g.
  `yttdl <url> --translate en` gets English out of almost any captioned video.
  If translation to `LANG` isn't offered, the original language is kept.

**Batch options:**

- `-f, --from-file PATH` — read sources from a file, one URL/ID per line
  (`#` comments and blank lines ignored). Combine with positional sources.
- **Resume for free** — already-downloaded videos are skipped on re-run; pass
  `--overwrite` to force a re-fetch.
- `--report PATH` — write a JSON manifest (counts + per-video status/errors),
  so failures in a large run are inspectable afterward.

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

### Free proxy pool (`--proxy-pool`)

Rotate through a free public proxy list ([proxifly](https://github.com/proxifly/free-proxy-list))
and switch proxy on each IP block:

```bash
uv run yttdl <url> --proxy-pool
uv run yttdl <url> --proxy-pool-url https://example.com/my-list.json   # custom source
```

**Best-effort only.** Free proxies are mostly datacenter IPs that YouTube
blocks, and they die constantly — expect most to fail; the pool tries up to
`max_attempts` (12) per video, elite/high-score first. Good as a free fallback,
but **residential proxies (Webshare) are the reliable path** for real volume.
In code: `download_transcripts(..., proxy_pool=ProxyPool())`.

## Scope & the commercial path

This is the **core**, built to be wrapped later. Deliberately *not* included yet
(decide when you pick a business model): the hosted API / SaaS layer, auth,
billing, and the official-YouTube-Data-API vs. scraping decision.

> ⚠️ Personal transcript downloading is routine. Commercially reselling scraped
> transcripts runs against YouTube's Terms of Service, and residential-proxy
> scraping is legally gray — validate this before building the commercial layer.
> Many commercial products route through the official YouTube Data API instead.
