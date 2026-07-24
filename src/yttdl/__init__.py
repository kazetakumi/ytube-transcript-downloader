"""yttdl — download YouTube captions as plain text, in batch.

Library entry points:
    from yttdl import fetch_transcript, download_transcripts, ProxySettings
"""

from .cache import TranscriptCache
from .cli import main
from .core import (
    Result,
    download_transcripts,
    fetch_transcript,
    read_sources_file,
    write_report,
)
from .proxies import ProxySettings
from .proxy_pool import ProxyPool
from .transcript import (
    TranscriptBlocked,
    TranscriptFetcher,
    TranscriptUnavailable,
)

__all__ = [
    "fetch_transcript",
    "download_transcripts",
    "read_sources_file",
    "write_report",
    "Result",
    "ProxySettings",
    "ProxyPool",
    "TranscriptFetcher",
    "TranscriptCache",
    "TranscriptUnavailable",
    "TranscriptBlocked",
    "main",
]
