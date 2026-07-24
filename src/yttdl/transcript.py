"""Fetch one video's transcript as plain text, with retry + cache.

Wraps ``youtube-transcript-api``'s instance API. ``find_transcript`` already
prefers manually-created captions and falls back to auto-generated ones, which
is the language policy we want, so we lean on it directly.
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    RequestBlocked,
    YouTubeTranscriptApi,
    YouTubeRequestFailed,
)

from .cache import TranscriptCache
from .proxies import ProxySettings

# Ban / transient signals worth retrying (IpBlocked subclasses RequestBlocked).
# Everything else under CouldNotRetrieveTranscript means "no transcript" — skip.
_RETRYABLE = (RequestBlocked, YouTubeRequestFailed)


class TranscriptUnavailable(Exception):
    """The video has no usable transcript (disabled, none, or unavailable)."""


class TranscriptBlocked(Exception):
    """Still blocked after exhausting retries — an IP/proxy problem."""


class TranscriptFetcher:
    """Reusable fetcher: one API session, shared cache and retry policy."""

    def __init__(
        self,
        *,
        proxy: Optional[ProxySettings] = None,
        cache: Optional[TranscriptCache] = None,
        languages: Sequence[str] = ("en",),
        max_retries: int = 3,
        backoff: float = 2.0,
    ):
        proxy_config = proxy.to_proxy_config() if proxy else None
        self._api = YouTubeTranscriptApi(proxy_config=proxy_config)
        self._cache = cache
        self.languages = tuple(languages)
        self.max_retries = max_retries
        self.backoff = backoff

    def fetch_text(self, video_id: str) -> str:
        """Return the transcript as plain text, one caption line per row.

        Raises ``TranscriptUnavailable`` or ``TranscriptBlocked`` on failure.
        """
        primary = self.languages[0]
        if self._cache:
            cached = self._cache.get(video_id, primary)
            if cached is not None:
                return cached

        segments = self._fetch_with_retry(video_id)
        text = "\n".join(
            line for seg in segments if (line := seg["text"].strip())
        )

        if self._cache:
            self._cache.put(video_id, primary, text)
        return text

    def _fetch_with_retry(self, video_id: str) -> list[dict]:
        attempt = 0
        while True:
            try:
                transcript = self._api.list(video_id).find_transcript(
                    list(self.languages)
                )
                return transcript.fetch().to_raw_data()
            except _RETRYABLE as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise TranscriptBlocked(str(exc)) from exc
                time.sleep(self.backoff**attempt)
            except CouldNotRetrieveTranscript as exc:
                # Not a block (checked above) — genuinely no transcript.
                raise TranscriptUnavailable(str(exc)) from exc
