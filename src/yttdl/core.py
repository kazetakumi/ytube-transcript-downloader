"""Orchestration: the public library surface.

Ties enumeration, fetching, cache, and file-writing together. This is the layer
a future service (API / SaaS) would call — it takes plain arguments and returns
plain data, with no CLI or I/O assumptions baked in beyond writing output files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

from .cache import TranscriptCache
from .enumerate import expand_sources
from .proxies import ProxySettings
from .transcript import (
    TranscriptBlocked,
    TranscriptFetcher,
    TranscriptUnavailable,
)


@dataclass
class Result:
    video_id: str
    ok: bool
    path: Optional[Path] = None
    error: Optional[str] = None


def _make_fetcher(
    proxy: Optional[ProxySettings],
    cache_dir: Optional[Union[str, Path]],
    languages: Sequence[str],
    max_retries: int,
    backoff: float,
) -> tuple[TranscriptFetcher, ProxySettings]:
    proxy = proxy or ProxySettings.from_env()
    cache = TranscriptCache(cache_dir) if cache_dir else None
    fetcher = TranscriptFetcher(
        proxy=proxy,
        cache=cache,
        languages=languages,
        max_retries=max_retries,
        backoff=backoff,
    )
    return fetcher, proxy


def fetch_transcript(
    source: str,
    *,
    languages: Sequence[str] = ("en",),
    proxy: Optional[ProxySettings] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    max_retries: int = 3,
    backoff: float = 2.0,
) -> str:
    """Fetch a single video's transcript as plain text.

    ``source`` may be a video URL or a bare video ID. Raises on failure.
    """
    fetcher, proxy = _make_fetcher(
        proxy, cache_dir, languages, max_retries, backoff
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
    proxy: Optional[ProxySettings] = None,
    cache_dir: Optional[Union[str, Path]] = None,
    max_retries: int = 3,
    backoff: float = 2.0,
    on_progress: Optional[Callable[[Result], None]] = None,
) -> list[Result]:
    """Expand ``sources`` into videos and write one ``<video_id>.txt`` each.

    Videos without a transcript (or still blocked after retries) are skipped and
    recorded in the returned results rather than aborting the batch. Pass
    ``on_progress`` to observe each result as it completes.
    """
    fetcher, proxy = _make_fetcher(
        proxy, cache_dir, languages, max_retries, backoff
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    video_ids = expand_sources(sources, proxy=proxy.to_ytdlp_proxy())

    results: list[Result] = []
    for vid in video_ids:
        try:
            text = fetcher.fetch_text(vid)
            path = out / f"{vid}.txt"
            path.write_text(text, encoding="utf-8")
            result = Result(vid, ok=True, path=path)
        except (TranscriptUnavailable, TranscriptBlocked) as exc:
            result = Result(vid, ok=False, error=f"{type(exc).__name__}: {exc}")
        results.append(result)
        if on_progress:
            on_progress(result)
    return results
