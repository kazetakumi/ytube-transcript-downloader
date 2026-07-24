"""Fetch a video's transcript as plain text.

Two backends fetch captions by different routes:

- **yt-dlp** (default) pulls captions through YouTube's player API with a real
  browser TLS fingerprint — far more resistant to IP blocks; works from a plain
  IP without a proxy.
- **youtube-transcript-api** scrapes the ``timedtext`` endpoint; kept as a
  fallback for the rare video yt-dlp can't get.

``TranscriptFetcher`` is the coordinator: it owns the cache and tries the
backends in order. A ``ProxyPool`` can be supplied to rotate proxies on blocks.
"""

from __future__ import annotations

import time
from typing import Optional, Sequence

import requests
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
from .proxy_pool import ProxyPool

# Ban / transient signals worth retrying (IpBlocked subclasses RequestBlocked).
# Everything else under CouldNotRetrieveTranscript means "no transcript" — skip.
_RETRYABLE = (RequestBlocked, YouTubeRequestFailed)
_POOL_TIMEOUT = 15  # seconds — so dead pool proxies fail fast


class TranscriptUnavailable(Exception):
    """The video has no usable transcript (disabled, none, or unavailable)."""


class TranscriptBlocked(Exception):
    """Still blocked after exhausting retries — an IP/proxy problem."""


def snippets_to_text(segments: Sequence[dict]) -> str:
    """Join caption segments into plain text, one non-empty line per row."""
    return "\n".join(line for seg in segments if (line := seg["text"].strip()))


class _TimedSession(requests.Session):
    """Session that applies a default timeout so dead proxies don't hang."""

    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", self._timeout)
        return super().request(*args, **kwargs)


class ApiBackend:
    """Fetch captions via youtube-transcript-api (timedtext scraping)."""

    def __init__(
        self,
        *,
        proxy: Optional[ProxySettings] = None,
        proxy_pool: Optional[ProxyPool] = None,
        languages: Sequence[str] = ("en",),
        fallback_any: bool = False,
        translate_to: Optional[str] = None,
        max_retries: int = 3,
        backoff: float = 2.0,
    ):
        self.pool = proxy_pool
        self.languages = tuple(languages)
        self.fallback_any = fallback_any
        self.translate_to = translate_to
        self.max_retries = max_retries
        self.backoff = backoff
        # Fixed client only when not rotating a pool.
        self._api = (
            None
            if proxy_pool is not None
            else YouTubeTranscriptApi(
                proxy_config=proxy.to_proxy_config() if proxy else None
            )
        )

    def fetch(self, video_id: str) -> str:
        if self.pool is not None:
            return snippets_to_text(self._fetch_via_pool(video_id))
        return snippets_to_text(self._fetch_with_retry(video_id))

    def _fetch_with_retry(self, video_id: str) -> list[dict]:
        attempt = 0
        while True:
            try:
                return self._extract(self._api, video_id)
            except _RETRYABLE as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise TranscriptBlocked(str(exc)) from exc
                time.sleep(self.backoff**attempt)
            except CouldNotRetrieveTranscript as exc:
                raise TranscriptUnavailable(str(exc)) from exc

    def _fetch_via_pool(self, video_id: str) -> list[dict]:
        attempts = min(len(self.pool), self.pool.max_attempts) or 1
        last: Optional[Exception] = None
        for _ in range(attempts):
            try:
                return self._extract(self._client_for(self.pool.next()), video_id)
            except _RETRYABLE as exc:
                last = TranscriptBlocked(str(exc))  # blocked proxy — rotate
            except CouldNotRetrieveTranscript as exc:
                # Genuine "no transcript" fails on every proxy — stop early.
                raise TranscriptUnavailable(str(exc)) from exc
            except Exception as exc:  # dead proxy / connection error — rotate
                last = exc
        raise last or TranscriptBlocked(f"proxy pool exhausted for {video_id}")

    @staticmethod
    def _client_for(proxy_url: Optional[str]) -> YouTubeTranscriptApi:
        if proxy_url is None:
            return YouTubeTranscriptApi()
        session = _TimedSession(_POOL_TIMEOUT)
        session.proxies = {"http": proxy_url, "https": proxy_url}
        return YouTubeTranscriptApi(http_client=session)

    def _extract(self, api: YouTubeTranscriptApi, video_id: str) -> list[dict]:
        transcript = self._select(api.list(video_id))
        if self.translate_to and transcript.language_code != self.translate_to:
            transcript = self._maybe_translate(transcript)
        return transcript.fetch().to_raw_data()

    def _select(self, transcript_list):
        try:
            return transcript_list.find_transcript(list(self.languages))
        except NoTranscriptFound:
            if self.fallback_any or self.translate_to:
                for transcript in transcript_list:
                    return transcript
            raise

    def _maybe_translate(self, transcript):
        try:
            return transcript.translate(self.translate_to)
        except (NotTranslatable, TranslationLanguageNotAvailable):
            return transcript


class TranscriptFetcher:
    """Coordinator: cache + ordered backends. Reusable across many videos."""

    def __init__(
        self,
        *,
        proxy: Optional[ProxySettings] = None,
        proxy_pool: Optional[ProxyPool] = None,
        cache: Optional[TranscriptCache] = None,
        languages: Sequence[str] = ("en",),
        fallback_any: bool = False,
        translate_to: Optional[str] = None,
        max_retries: int = 3,
        backoff: float = 2.0,
        backends: Sequence[str] = ("ytdlp", "api"),
    ):
        self._cache = cache
        self._key = translate_to or languages[0]
        self._backends = [
            self._build_backend(
                name, proxy, proxy_pool, languages,
                fallback_any, translate_to, max_retries, backoff,
            )
            for name in backends
        ]

    @staticmethod
    def _build_backend(
        name, proxy, proxy_pool, languages, fallback_any, translate_to, max_retries, backoff
    ):
        if name == "ytdlp":
            from .ytdlp_fetch import YtdlpBackend  # local import: heavy module

            return YtdlpBackend(
                proxy=proxy.to_ytdlp_proxy() if proxy else None,
                proxy_pool=proxy_pool,
                languages=languages,
                fallback_any=fallback_any,
                translate_to=translate_to,
            )
        if name == "api":
            return ApiBackend(
                proxy=proxy,
                proxy_pool=proxy_pool,
                languages=languages,
                fallback_any=fallback_any,
                translate_to=translate_to,
                max_retries=max_retries,
                backoff=backoff,
            )
        raise ValueError(f"unknown backend: {name!r}")

    def fetch_text(self, video_id: str) -> str:
        """Return the transcript as plain text, trying each backend in order.

        Raises ``TranscriptUnavailable`` or ``TranscriptBlocked`` if all fail.
        """
        if self._cache:
            cached = self._cache.get(video_id, self._key)
            if cached is not None:
                return cached

        last_exc: Optional[Exception] = None
        for backend in self._backends:
            try:
                text = backend.fetch(video_id)
            except (TranscriptUnavailable, TranscriptBlocked) as exc:
                last_exc = exc
                continue
            if self._cache:
                self._cache.put(video_id, self._key, text)
            return text

        raise last_exc  # at least one backend always runs
