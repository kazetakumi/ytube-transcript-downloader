"""yt-dlp caption backend.

Downloads captions through YouTube's player API (the same path used for
enumeration), which is far more resistant to IP blocks than scraping the
``timedtext`` endpoint. Captions are fetched as ``json3`` and flattened to text.

Language policy mirrors the API backend: requested languages in priority order,
then (if ``fallback_any``/translation is on) any available track. Translation is
free here — YouTube exposes auto-translated tracks under ``automatic_captions``,
so "translate to X" is just "request track X".
"""

from __future__ import annotations

import glob
import json
import os
import tempfile
from typing import Optional, Sequence

from yt_dlp import YoutubeDL

from ._ytdlp import impersonate_target
from .proxy_pool import ProxyPool
from .transcript import TranscriptUnavailable, snippets_to_text

_SOCKET_TIMEOUT = 15  # seconds — so dead pool proxies fail fast


def _json3_to_text(path: str) -> str:
    data = json.load(open(path, encoding="utf-8"))
    segments = []
    for event in data.get("events", []):
        text = "".join(seg.get("utf8", "") for seg in (event.get("segs") or []))
        segments.append({"text": text})
    return snippets_to_text(segments)


class YtdlpBackend:
    def __init__(
        self,
        *,
        proxy: Optional[str] = None,
        proxy_pool: Optional[ProxyPool] = None,
        languages: Sequence[str] = ("en",),
        fallback_any: bool = False,
        translate_to: Optional[str] = None,
    ):
        self.proxy = proxy
        self.pool = proxy_pool
        self.languages = tuple(languages)
        self.fallback_any = fallback_any
        self.translate_to = translate_to

    def fetch(self, video_id: str) -> str:
        if self.pool is None:
            return self._fetch_once(video_id, self.proxy)

        # Rotate through the pool until one proxy yields captions.
        attempts = min(len(self.pool), self.pool.max_attempts) or 1
        for _ in range(attempts):
            try:
                return self._fetch_once(video_id, self.pool.next())
            except TranscriptUnavailable:
                continue  # dead / blocked proxy — try the next one
        raise TranscriptUnavailable(f"proxy pool exhausted for {video_id}")

    def _fetch_once(self, video_id: str, proxy: Optional[str]) -> str:
        # When translating, the desired output track *is* the target language —
        # YouTube auto-translates, so we just ask for it directly.
        desired = [self.translate_to] if self.translate_to else list(self.languages)
        url = f"https://www.youtube.com/watch?v={video_id}"

        with tempfile.TemporaryDirectory() as tmp:
            info = self._download_subs(url, tmp, desired, proxy)
            text = self._read_first(tmp, video_id, desired)
            if text is not None:
                return text

            if self.fallback_any or self.translate_to:
                fallback = self._fallback_lang(info)
                if fallback:
                    self._download_subs(url, tmp, [fallback], proxy)
                    text = self._read_first(tmp, video_id, [fallback])
                    if text is not None:
                        return text

        raise TranscriptUnavailable(f"no captions available for {video_id}")

    def _download_subs(
        self, url: str, tmp: str, langs: Sequence[str], proxy: Optional[str]
    ) -> dict:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(langs),
            "subtitlesformat": "json3",
            "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "socket_timeout": _SOCKET_TIMEOUT,
        }
        if (target := impersonate_target()) is not None:
            opts["impersonate"] = target
        if proxy:
            opts["proxy"] = proxy
        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True) or {}
        except Exception:
            # yt-dlp couldn't retrieve it (dead proxy, block, network); let the
            # caller fall through to fallback / pool rotation / next backend.
            return {}

    @staticmethod
    def _read_first(tmp: str, video_id: str, langs: Sequence[str]) -> Optional[str]:
        for lang in langs:
            exact = os.path.join(tmp, f"{video_id}.{lang}.json3")
            if os.path.exists(exact):
                return _json3_to_text(exact)
            # yt-dlp may suffix regional variants (en-US, en-orig, …).
            matches = sorted(glob.glob(os.path.join(tmp, f"{video_id}.{lang}*.json3")))
            if matches:
                return _json3_to_text(matches[0])
        return None

    @staticmethod
    def _fallback_lang(info: dict) -> Optional[str]:
        subs = info.get("subtitles") or {}
        autos = info.get("automatic_captions") or {}
        if subs:
            return next(iter(subs))  # prefer a real (manual) caption
        if autos:
            return next(iter(autos))
        return None
