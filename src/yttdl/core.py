"""Orchestration: the public library surface.

Ties enumeration, fetching, cache, and file-writing together. This is the layer
a future service (API / SaaS) would call — it takes plain arguments and returns
plain data, with no CLI or I/O assumptions baked in beyond writing output files.

Fetching is deliberately sequential (one video at a time) to stay gentle on
YouTube and reduce the chance of an IP block.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

from .cache import TranscriptCache
from .enumerate import expand_sources
from .proxies import ProxySettings
from .proxy_pool import ProxyPool
from .transcript import (
    TranscriptBlocked,
    TranscriptFetcher,
    TranscriptUnavailable,
)

# Result.status values.
DOWNLOADED = "downloaded"
SKIPPED_EXISTING = "skipped_existing"
FAILED = "failed"


@dataclass
class Result:
    video_id: str
    status: str  # DOWNLOADED | SKIPPED_EXISTING | FAILED
    path: Optional[Path] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """True if the transcript is on disk (freshly downloaded or already there)."""
        return self.status in (DOWNLOADED, SKIPPED_EXISTING)


def read_sources_file(path: Union[str, Path]) -> list[str]:
    """Read sources from a text file: one URL/ID per line.

    Blank lines and ``#`` comments (whole-line or trailing) are ignored.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [stripped for line in lines if (stripped := line.split("#", 1)[0].strip())]


def _make_fetcher(
    proxy: Optional[ProxySettings],
    proxy_pool: Optional[ProxyPool],
    cache_dir: Optional[Union[str, Path]],
    languages: Sequence[str],
    fallback_any: bool,
    translate_to: Optional[str],
    max_retries: int,
    backoff: float,
) -> tuple[TranscriptFetcher, ProxySettings]:
    proxy = proxy or ProxySettings.from_env()
    cache = TranscriptCache(cache_dir) if cache_dir else None
    fetcher = TranscriptFetcher(
        proxy=proxy,
        proxy_pool=proxy_pool,
        cache=cache,
        languages=languages,
        fallback_any=fallback_any,
        translate_to=translate_to,
        max_retries=max_retries,
        backoff=backoff,
    )
    return fetcher, proxy


def fetch_transcript(
    source: str,
    *,
    languages: Sequence[str] = ("en",),
    fallback_any: bool = False,
    translate_to: Optional[str] = None,
    proxy: Optional[ProxySettings] = None,
    proxy_pool: Optional[ProxyPool] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    max_retries: int = 3,
    backoff: float = 2.0,
) -> str:
    """Fetch a single video's transcript as plain text.

    ``source`` may be a video URL or a bare video ID. Raises on failure.
    """
    fetcher, proxy = _make_fetcher(
        proxy, proxy_pool, cache_dir, languages, fallback_any, translate_to,
        max_retries, backoff,
    )
    ids = expand_sources([source], proxy=proxy.to_ytdlp_proxy())
    if not ids:
        raise ValueError(f"No video found for source: {source!r}")
    return fetcher.fetch_text(ids[0])


def download_transcripts(
    sources: Sequence[str],
    *,
    out_dir: Union[str, Path] = "transcripts",
    languages: Sequence[str] = ("en",),
    fallback_any: bool = False,
    translate_to: Optional[str] = None,
    proxy: Optional[ProxySettings] = None,
    proxy_pool: Optional[ProxyPool] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    max_retries: int = 3,
    backoff: float = 2.0,
    skip_existing: bool = True,
    on_progress: Optional[Callable[[Result], None]] = None,
) -> list[Result]:
    """Expand ``sources`` into videos and write one ``<video_id>.txt`` each.

    Videos are fetched one at a time. When ``skip_existing`` is true (default),
    a video whose output file already exists is left untouched — making a re-run
    a cheap way to resume a large batch. Videos without a transcript (or still
    blocked after retries) are recorded as failures rather than aborting the
    batch. Pass ``on_progress`` to observe each result as it completes.
    """
    fetcher, proxy = _make_fetcher(
        proxy, proxy_pool, cache_dir, languages, fallback_any, translate_to,
        max_retries, backoff,
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    video_ids = expand_sources(sources, proxy=proxy.to_ytdlp_proxy())

    results: list[Result] = []
    for vid in video_ids:
        path = out / f"{vid}.txt"
        if skip_existing and path.exists():
            result = Result(vid, SKIPPED_EXISTING, path=path)
        else:
            try:
                text = fetcher.fetch_text(vid)
                path.write_text(text, encoding="utf-8")
                result = Result(vid, DOWNLOADED, path=path)
            except (TranscriptUnavailable, TranscriptBlocked) as exc:
                result = Result(vid, FAILED, error=f"{type(exc).__name__}: {exc}")
        results.append(result)
        if on_progress:
            on_progress(result)
    return results


def write_report(results: Sequence[Result], path: Union[str, Path]) -> None:
    """Write a JSON manifest of the batch: counts plus per-video status."""
    data = {
        "total": len(results),
        "downloaded": sum(r.status == DOWNLOADED for r in results),
        "skipped_existing": sum(r.status == SKIPPED_EXISTING for r in results),
        "failed": sum(r.status == FAILED for r in results),
        "videos": [
            {
                "video_id": r.video_id,
                "status": r.status,
                "path": str(r.path) if r.path else None,
                "error": r.error,
            }
            for r in results
        ],
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
