"""Fetch one video's transcript as plain text, with retry + cache.

Wraps ``youtube-transcript-api``'s instance API. Language resolution goes:

1. ``find_transcript(languages)`` — the requested codes in priority order,
   manually-created captions preferred over auto-generated ones.
2. If none match and ``fallback_any`` (or a translation target) is set, take any
   available transcript, whatever its language.
3. If ``translate_to`` is set and the chosen transcript isn't already in that
   language, machine-translate it via YouTube (best-effort).
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    NotTranslatable,
    RequestBlocked,
    TranslationLanguageNotAvailable,
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
        fallback_any: bool = False,
        translate_to: Optional[str] = None,
        max_retries: int = 3,
        backoff: float = 2.0,
    ):
        proxy_config = proxy.to_proxy_config() if proxy else None
        self._api = YouTubeTranscriptApi(proxy_config=proxy_config)
        self._cache = cache
        self.languages = tuple(languages)
        self.fallback_any = fallback_any
        self.translate_to = translate_to
        self.max_retries = max_retries
        self.backoff = backoff

    def fetch_text(self, video_id: str) -> str:
        """Return the transcript as plain text, one caption line per row.

        Raises ``TranscriptUnavailable`` or ``TranscriptBlocked`` on failure.
        """
        # Cache slot reflects the desired output language.
        key = self.translate_to or self.languages[0]
        if self._cache:
            cached = self._cache.get(video_id, key)
            if cached is not None:
                return cached

        segments = self._fetch_with_retry(video_id)
        text = "\n".join(
            line for seg in segments if (line := seg["text"].strip())
        )

        if self._cache:
            self._cache.put(video_id, key, text)
        return text

    def _fetch_with_retry(self, video_id: str) -> list[dict]:
        attempt = 0
        while True:
            try:
                transcript = self._select(self._api.list(video_id))
                if self.translate_to and transcript.language_code != self.translate_to:
                    transcript = self._maybe_translate(transcript)
                return transcript.fetch().to_raw_data()
            except _RETRYABLE as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise TranscriptBlocked(str(exc)) from exc
                time.sleep(self.backoff**attempt)
            except CouldNotRetrieveTranscript as exc:
                # Not a block (checked above) — genuinely no transcript.
                raise TranscriptUnavailable(str(exc)) from exc

    def _select(self, transcript_list):
        """Pick a transcript: requested languages first, else any available."""
        try:
            return transcript_list.find_transcript(list(self.languages))
        except NoTranscriptFound:
            if self.fallback_any or self.translate_to:
                for transcript in transcript_list:  # first available, any language
                    return transcript
            raise

    def _maybe_translate(self, transcript):
        """Translate to ``self.translate_to``, or keep the original if we can't."""
        try:
            return transcript.translate(self.translate_to)
        except (NotTranslatable, TranslationLanguageNotAvailable):
            return transcript
