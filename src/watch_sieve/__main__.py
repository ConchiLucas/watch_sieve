from __future__ import annotations

import argparse
import json

from watch_sieve.config import load_config
from watch_sieve.crawler import WatchCrawler
from watch_sieve.models import SiteConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch page content from specified sites.")
    parser.add_argument("--config", default="configs/sites.example.yaml")
    parser.add_argument("--url", help="Fetch a single URL instead of the config file")
    parser.add_argument("--wait-for", dest="wait_for", help="CSS selector to wait for in the browser")
    parser.add_argument("--selector", help="CSS selector for list titles")
    parser.add_argument("--browser", action="store_true", help="Skip HTTP and use Playwright")
    parser.add_argument("--json", action="store_true", help="Print full JSON results")
    args = parser.parse_args()

    sites = _sites_from_args(args)
    failures = 0
    with WatchCrawler() as crawler:
        results = [crawler.fetch_site(site) for site in sites]

    for result in results:
        if args.json:
            payload = result.model_dump(mode="json")
            payload.pop("html", None)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_result(result)
        if not result.ok:
            failures += 1

    if not args.json:
        ok = sum(1 for result in results if result.ok)
        print(f"\n{ok}/{len(results)} fetched")
    raise SystemExit(1 if failures else 0)


def _sites_from_args(args: argparse.Namespace) -> list[SiteConfig]:
    if args.url:
        return [
            SiteConfig(
                id="cli",
                name=args.url,
                url=args.url,
                wait_for=args.wait_for,
                css_selector=args.selector,
                force_browser=args.browser,
            )
        ]
    return load_config(args.config).sites


def _print_result(result) -> None:
    flag = "ok" if result.ok else "fail"
    engine = result.engine or "-"
    status = result.status_code if result.status_code is not None else "-"
    title = result.title or result.site_id or result.url
    print(f"[{flag}] {result.site_id or 'url'}  {engine}  {status}  {title}")
    print(f"     {result.url}")
    if result.final_url and result.final_url != result.url:
        print(f"     -> {result.final_url}")
    if result.error:
        print(f"     error: {result.error}")
    if result.items:
        print(f"     {len(result.items)} titles")
        for index, item in enumerate(result.items, start=1):
            print(f"     {index}. {item.title}")
    else:
        preview = result.content[:500].replace("\n", "\n     ")
        if preview:
            print(f"     {preview}")
    print()


if __name__ == "__main__":
    main()
