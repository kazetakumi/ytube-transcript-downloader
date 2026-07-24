"""Shared yt-dlp helpers."""

from __future__ import annotations


def impersonate_target():
    """Best browser-impersonation target for yt-dlp, or ``None`` if unavailable.

    With ``curl_cffi`` installed, yt-dlp can send a real browser's TLS
    fingerprint instead of its default client signature — the single biggest
    anti-ban win that needs no proxy. ``ImpersonateTarget("chrome")`` resolves
    to whatever Chrome build curl_cffi actually provides.
    """
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
    except Exception:
        return None
    return ImpersonateTarget("chrome")
