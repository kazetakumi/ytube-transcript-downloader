"""Filesystem cache for fetched transcripts.

Every fetch spends an IP's reputation, so never fetch the same video twice.
Keyed by video ID + requested language; the cached value is the plain text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union


class TranscriptCache:
    def __init__(self, directory: Union[str, Path]):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, video_id: str, lang: str) -> Path:
        return self.dir / f"{video_id}.{lang}.txt"

    def get(self, video_id: str, lang: str) -> Optional[str]:
        path = self._path(video_id, lang)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def put(self, video_id: str, lang: str, text: str) -> None:
        self._path(video_id, lang).write_text(text, encoding="utf-8")
