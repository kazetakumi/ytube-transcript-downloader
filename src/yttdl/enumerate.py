"""Turn any YouTube URL into a flat list of video IDs.

``youtube-transcript-api`` only takes a single video ID, so this is the piece
that makes batch input work: yt-dlp expands playlists, channels, and mixes into
their member video IDs without downloading anything.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from yt_dlp import YoutubeDL

from ._ytdlp import impersonate_target

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _normalize(source: str) -> str:
    """Accept bare 11-char video IDs alongside full URLs."""
    source = source.strip()
    if _VIDEO_ID_RE.match(source):
        return f"https://www.youtube.com/watch?v={source}"
    return source


def _ids_from_info(info: dict) -> list[str]:
    """Flatten a yt-dlp info dict into video IDs.

    A channel comes back as playlists-of-videos, so entries can nest one level;
    we walk both. ``extract_flat`` means each leaf entry is a video stub. Only
    real 11-char video IDs are kept — playlist/channel stubs are dropped so they
    never leak through as bogus "videos".
    """
    if not info:
        return []
    if "entries" in info:
        ids: list[str] = []
        for entry in info["entries"]:
            if entry:
                ids.extend(_ids_from_info(entry))
        return ids
    vid = info.get("id")
    return [vid] if vid and _VIDEO_ID_RE.match(vid) else []


def expand_sources(
    sources: Iterable[str], proxy: Optional[str] = None
) -> list[str]:
    """Expand URLs / playlist / channel / bare IDs into de-duplicated video IDs.

    Order is preserved (first occurrence wins). Sources that fail to resolve are
    skipped silently — per-video transcript errors are reported downstream.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
        # A /watch?v=X&list=Y URL means "this video" — take X, not the playlist.
        # Bare /playlist and /channel URLs have no video to pick, so they still
        # enumerate fully.
        "noplaylist": True,
    }
    if (target := impersonate_target()) is not None:
        opts["impersonate"] = target
    if proxy:
        opts["proxy"] = proxy

    ids: list[str] = []
    seen: set[str] = set()
    with YoutubeDL(opts) as ydl:
        for source in sources:
            try:
                info = ydl.extract_info(_normalize(source), download=False)
            except Exception:
                continue
            for vid in _ids_from_info(info):
                if vid not in seen:
                    seen.add(vid)
                    ids.append(vid)
    return ids
