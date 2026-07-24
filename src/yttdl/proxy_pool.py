"""Rotating pool of free public proxies (proxifly by default).

Free proxies are mostly datacenter IPs — YouTube blocks the majority, and they
die fast. So this is deliberately best-effort: on each block we rotate to the
next proxy and retry, up to a cap. Higher-anonymity, higher-score proxies are
tried first. For reliable throughput, use residential proxies (Webshare) via
``ProxySettings`` instead.
"""

from __future__ import annotations

from typing import Optional, Sequence

import requests

_PROXIFLY = (
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main"
    "/proxies/protocols/{p}/data.json"
)
DEFAULT_SOURCES = (_PROXIFLY.format(p="http"), _PROXIFLY.format(p="https"))

# Prefer proxies that reveal less about the client.
_ANON_RANK = {"elite": 0, "anonymous": 1, "transparent": 2}


class ProxyPool:
    """Lazily-loaded, rotating list of ``http://ip:port`` proxy URLs."""

    def __init__(
        self,
        sources: Sequence[str] = DEFAULT_SOURCES,
        *,
        limit: int = 200,
        timeout: float = 15.0,
        max_attempts: int = 12,
    ):
        self._sources = tuple(sources)
        self._limit = limit
        self._timeout = timeout
        self.max_attempts = max_attempts  # cap on proxies tried per video
        self._proxies: Optional[list[str]] = None
        self._idx = 0

    def _load(self) -> list[str]:
        entries: list = []
        for source in self._sources:
            try:
                entries.extend(requests.get(source, timeout=self._timeout).json())
            except Exception:
                continue

        ranked: list[tuple] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ip, port = entry.get("ip"), entry.get("port")
            if not ip or not port:
                continue
            hostport = f"{ip}:{port}"
            if hostport in seen:
                continue
            seen.add(hostport)
            rank = _ANON_RANK.get(entry.get("anonymity"), 3)
            score = entry.get("score") or 0
            ranked.append((rank, -score, f"http://{hostport}"))

        ranked.sort()  # elite first, then higher score
        return [url for _, _, url in ranked[: self._limit]]

    def _ensure(self) -> list[str]:
        if self._proxies is None:
            self._proxies = self._load()
        return self._proxies

    def next(self) -> Optional[str]:
        """Next proxy URL, cycling through the pool. ``None`` if the pool is empty."""
        proxies = self._ensure()
        if not proxies:
            return None
        url = proxies[self._idx % len(proxies)]
        self._idx += 1
        return url

    def __len__(self) -> int:
        return len(self._ensure())
