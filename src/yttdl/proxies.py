"""Vendor-neutral proxy configuration.

The anti-ban layer. YouTube blocks datacenter IPs aggressively, so real
throughput needs rotating residential proxies. This module keeps the rest of
the code vendor-agnostic: callers pass a ``ProxySettings`` and we translate it
to whatever ``youtube-transcript-api`` and ``yt-dlp`` each expect.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from youtube_transcript_api.proxies import (
    GenericProxyConfig,
    ProxyConfig,
    WebshareProxyConfig,
)

_WEBSHARE_HOST = "p.webshare.io"
_WEBSHARE_PORT = 80


@dataclass
class ProxySettings:
    """Either a BYO generic HTTP/SOCKS proxy, or a Webshare residential pool.

    Webshare takes precedence when its credentials are present.
    """

    http_url: Optional[str] = None
    https_url: Optional[str] = None
    webshare_username: Optional[str] = None
    webshare_password: Optional[str] = None

    @classmethod
    def from_env(cls) -> "ProxySettings":
        """Read proxy settings from the environment.

        ``YTTDL_PROXY_HTTP`` / ``YTTDL_PROXY_HTTPS`` for a generic proxy (falls
        back to the conventional ``HTTP_PROXY`` / ``HTTPS_PROXY``), and
        ``YTTDL_WEBSHARE_USER`` / ``YTTDL_WEBSHARE_PASS`` for Webshare.
        """
        return cls(
            http_url=os.getenv("YTTDL_PROXY_HTTP") or os.getenv("HTTP_PROXY"),
            https_url=os.getenv("YTTDL_PROXY_HTTPS") or os.getenv("HTTPS_PROXY"),
            webshare_username=os.getenv("YTTDL_WEBSHARE_USER"),
            webshare_password=os.getenv("YTTDL_WEBSHARE_PASS"),
        )

    @property
    def is_configured(self) -> bool:
        return self.to_proxy_config() is not None

    def to_proxy_config(self) -> Optional[ProxyConfig]:
        """The proxy object ``youtube-transcript-api`` expects, or ``None``."""
        if self.webshare_username and self.webshare_password:
            return WebshareProxyConfig(
                proxy_username=self.webshare_username,
                proxy_password=self.webshare_password,
            )
        if self.http_url or self.https_url:
            return GenericProxyConfig(http_url=self.http_url, https_url=self.https_url)
        return None

    def to_ytdlp_proxy(self) -> Optional[str]:
        """A single proxy URL string for yt-dlp's ``proxy`` option, or ``None``.

        yt-dlp only handles enumeration here (listing a playlist's videos),
        which is far lighter than transcript fetching, so one endpoint is fine.
        """
        if self.webshare_username and self.webshare_password:
            return (
                f"http://{self.webshare_username}:{self.webshare_password}"
                f"@{_WEBSHARE_HOST}:{_WEBSHARE_PORT}"
            )
        return self.https_url or self.http_url
