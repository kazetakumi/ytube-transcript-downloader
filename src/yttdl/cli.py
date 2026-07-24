"""Command-line interface. Thin wrapper over ``core.download_transcripts``."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .core import (
    DOWNLOADED,
    FAILED,
    SKIPPED_EXISTING,
    Result,
    download_transcripts,
    read_sources_file,
    write_report,
)
from .proxies import ProxySettings
from .proxy_pool import DEFAULT_SOURCES, ProxyPool


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yttdl",
        description="Download YouTube captions as plain text. "
        "Accepts video, playlist, and channel URLs (or bare video IDs).",
    )
    parser.add_argument("sources", nargs="*", help="video / playlist / channel URLs or IDs")
    parser.add_argument(
        "-f",
        "--from-file",
        metavar="PATH",
        help="read sources from a file (one URL/ID per line, # comments allowed)",
    )
    parser.add_argument("-o", "--out", default="transcripts", help="output directory (default: transcripts)")
    parser.add_argument(
        "-l",
        "--lang",
        default="en",
        help="comma-separated language codes in priority order (default: en)",
    )
    parser.add_argument(
        "--fallback-any",
        action="store_true",
        help="if none of --lang are available, use any transcript the video has",
    )
    parser.add_argument(
        "--translate",
        metavar="LANG",
        help="translate the transcript to LANG when it isn't already (implies --fallback-any)",
    )
    parser.add_argument("--cache", metavar="DIR", help="cache directory (skips re-fetching)")
    parser.add_argument("--proxy", metavar="URL", help="generic HTTP/SOCKS proxy URL (else read from env)")
    parser.add_argument(
        "--proxy-pool",
        action="store_true",
        help="rotate through a free proxy pool (proxifly) on IP blocks — best-effort",
    )
    parser.add_argument(
        "--proxy-pool-url",
        metavar="URL",
        action="append",
        help="proxy-list JSON source for --proxy-pool (repeatable; default: proxifly)",
    )
    parser.add_argument("--retries", type=int, default=3, help="retries when blocked (default: 3)")
    parser.add_argument("--backoff", type=float, default=2.0, help="backoff base seconds (default: 2.0)")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="re-fetch videos even if their output file already exists",
    )
    parser.add_argument("--report", metavar="PATH", help="write a JSON run report to PATH")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print the final summary")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    sources = list(args.sources)
    if args.from_file:
        sources.extend(read_sources_file(args.from_file))
    if not sources:
        parser.error("provide at least one source (positional or --from-file)")

    proxy = ProxySettings.from_env()
    if args.proxy:
        proxy.http_url = args.proxy
        proxy.https_url = args.proxy

    proxy_pool = None
    if args.proxy_pool or args.proxy_pool_url:
        proxy_pool = ProxyPool(args.proxy_pool_url or list(DEFAULT_SOURCES))
        if not args.quiet:
            print(f"Loaded {len(proxy_pool)} proxies into the rotation pool.")

    def on_progress(result: Result) -> None:
        if args.quiet:
            return
        if result.status == DOWNLOADED:
            print(f"  ok    {result.video_id}  -> {result.path}")
        elif result.status == SKIPPED_EXISTING:
            print(f"  have  {result.video_id}  (already saved)")
        else:
            print(f"  fail  {result.video_id}  ({result.error})")

    results = download_transcripts(
        sources,
        out_dir=args.out,
        languages=tuple(args.lang.split(",")),
        fallback_any=args.fallback_any,
        translate_to=args.translate,
        proxy=proxy,
        proxy_pool=proxy_pool,
        cache_dir=args.cache,
        max_retries=args.retries,
        backoff=args.backoff,
        skip_existing=not args.overwrite,
        on_progress=on_progress,
    )

    downloaded = sum(r.status == DOWNLOADED for r in results)
    existing = sum(r.status == SKIPPED_EXISTING for r in results)
    failed = sum(r.status == FAILED for r in results)
    print(
        f"\nDone: {downloaded} downloaded, {existing} already present, "
        f"{failed} failed, {len(results)} total -> {args.out}/"
    )

    if args.report:
        write_report(results, args.report)
        print(f"Report written -> {args.report}")

    # Non-zero exit only if we found videos but none are on disk.
    return 1 if results and (downloaded + existing) == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
