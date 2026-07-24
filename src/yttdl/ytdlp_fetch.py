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
from .transcript import TranscriptUnavailable, snippets_to_text


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
        languages: Sequence[str] = ("en",),
        fallback_any: bool = False,
        translate_to: Optional[str] = None,
    ):
        self.proxy = proxy
        self.languages = tuple(languages)
        self.fallback_any = fallback_any
        self.translate_to = translate_to

    def fetch(self, video_id: str) -> str:
        # When translating, the desired output track *is* the target language —
        # YouTube auto-translates, so we just ask for it directly.
        desired = [self.translate_to] if self.translate_to else list(self.languages)
        url = f"https://www.youtube.com/watch?v={video_id}"

        with tempfile.TemporaryDirectory() as tmp:
            info = self._download_subs(url, tmp, desired)
            text = self._read_first(tmp, video_id, desired)
            if text is not None:
                return text

            if self.fallback_any or self.translate_to:
                fallback = self._fallback_lang(info)
                if fallback:
                    self._download_subs(url, tmp, [fallback])
                    text = self._read_first(tmp, video_id, [fallback])
                    if text is not None:
                        return text

        raise TranscriptUnavailable(f"no captions available for {video_id}")

    def _download_subs(self, url: str, tmp: str, langs: Sequence[str]) -> dict:
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
        }
        if (target := impersonate_target()) is not None:
            opts["impersonate"] = target
        if self.proxy:
            opts["proxy"] = self.proxy
        try:
            with YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True) or {}
        except Exception:
            # yt-dlp couldn't retrieve it; let the caller fall through to
            # fallback / the next backend rather than crashing the batch.
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
