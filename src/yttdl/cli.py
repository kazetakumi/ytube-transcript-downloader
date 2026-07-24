"""Command-line interface. Thin wrapper over ``core.download_transcripts``."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .core import Result, download_transcripts
from .proxies import ProxySettings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yttdl",
        description="Download YouTube captions as plain text. "
        "Accepts video, playlist, and channel URLs (or bare video IDs).",
    )
    parser.add_argument("sources", nargs="+", help="video / playlist / channel URLs or IDs")
    parser.add_argument("-o", "--out", default="transcripts", help="output directory (default: transcripts)")
    parser.add_argument(
        "-l",
        "--lang",
        default="en",
        help="comma-separated language codes in priority order (default: en)",
    )
    parser.add_argument("--cache", metavar="DIR", help="cache directory (skips re-fetching)")
    parser.add_argument("--proxy", metavar="URL", help="generic HTTP/SOCKS proxy URL (else read from env)")
    parser.add_argument("--retries", type=int, default=3, help="retries when blocked (default: 3)")
    parser.add_argument("--backoff", type=float, default=2.0, help="backoff base seconds (default: 2.0)")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print the final summary")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    proxy = ProxySettings.from_env()
    if args.proxy:
        proxy.http_url = args.proxy
        proxy.https_url = args.proxy

    def on_progress(result: Result) -> None:
        if args.quiet:
            return
        if result.ok:
            print(f"  ok    {result.video_id}  -> {result.path}")
        else:
            print(f"  skip  {result.video_id}  ({result.error})")

    results = download_transcripts(
        args.sources,
        out_dir=args.out,
        languages=tuple(args.lang.split(",")),
        proxy=proxy,
        cache_dir=args.cache,
        max_retries=args.retries,
        backoff=args.backoff,
        on_progress=on_progress,
    )

    ok = sum(1 for r in results if r.ok)
    failed = len(results) - ok
    print(f"\nDone: {ok} saved, {failed} skipped, {len(results)} total -> {args.out}/")
    # Non-zero exit only if we found videos but saved none.
    return 1 if results and ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
