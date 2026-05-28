"""
fetch_isap.py — Scraper for ISAP (Internetowy System Aktów Prawnych)

Downloads legal acts from the Sejm REST API:
  https://api.sejm.gov.pl/eli/acts/search

Saves each act as a line in a JSONL file under data/raw/.
Fields: {id, title, year, type, publisher, pos, eli, url, raw_text}

Usage:
    python scripts/fetch_isap.py --year 2024 --output data/raw/
    python scripts/fetch_isap.py --year-from 2020 --year-to 2024 --output data/raw/
    python scripts/fetch_isap.py --year 2024 --publisher MP --output data/raw/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import httpx
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

SEARCH_URL = "https://api.sejm.gov.pl/eli/acts/search"
TEXT_URL = "https://api.sejm.gov.pl/eli/acts/{eli}/text.html"

MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0
REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100

# Browser-like headers required — WAF blocks plain API user-agents
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Referer": "https://isap.sejm.gov.pl/",
}
JSON_HEADERS = {**HEADERS, "Accept": "application/json"}


def fetch_with_backoff(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = MAX_RETRIES,
) -> httpx.Response | None:
    backoff = INITIAL_BACKOFF
    for attempt in range(retries):
        try:
            response = client.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return response
            if response.status_code == 429 or response.status_code >= 500:
                log.warning(
                    "HTTP %d for %s, retry %d/%d in %.1fs",
                    response.status_code, url, attempt + 1, retries, backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            else:
                log.debug("HTTP %d for %s — skipping", response.status_code, url)
                return None
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            log.warning(
                "Request error for %s: %s — retry %d/%d", url, exc, attempt + 1, retries
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    log.error("Exhausted retries for %s", url)
    return None


def list_acts_for_year(
    client: httpx.Client, year: int, publisher: str | None = None
) -> list[dict]:
    acts: list[dict] = []
    offset = 0

    while True:
        params: dict = {"year": year, "limit": PAGE_SIZE, "offset": offset}
        if publisher:
            params["publisher"] = publisher

        response = fetch_with_backoff(client, SEARCH_URL, params=params, headers=JSON_HEADERS)
        if response is None:
            break

        try:
            data = response.json()
        except Exception:
            log.error("Invalid JSON from search endpoint at offset=%d", offset)
            break

        items: list[dict] = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            break

        acts.extend(items)
        log.info(
            "  year=%d offset=%d fetched %d acts (total: %d)",
            year, offset, len(items), len(acts),
        )

        if len(items) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.3)

    return acts


def fetch_act_text(client: httpx.Client, act: dict) -> str:
    eli = act.get("ELI", "")
    if not eli:
        return ""

    has_html = act.get("textHTML", False)
    if not has_html:
        return ""

    url = TEXT_URL.format(eli=eli)
    response = fetch_with_backoff(client, url, headers=HEADERS)
    if response is not None:
        return response.text
    return ""


def process_year(
    client: httpx.Client, year: int, output_dir: Path, publisher: str | None = None
) -> int:
    log.info("Processing year %d …", year)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{publisher.lower()}" if publisher else ""
    out_file = output_dir / f"acts_{year}{suffix}.jsonl"

    saved_ids: set[str] = set()
    if out_file.exists():
        with out_file.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    saved_ids.add(str(rec.get("id", "")))
                except json.JSONDecodeError:
                    pass
        log.info("  Resuming — %d acts already saved", len(saved_ids))

    acts_meta = list_acts_for_year(client, year, publisher)
    if not acts_meta:
        log.warning("No acts found for year=%d publisher=%s", year, publisher)
        return 0

    saved = len(saved_ids)
    with out_file.open("a", encoding="utf-8") as fh:
        for act in tqdm(acts_meta, desc=f"Acts {year}", unit="act"):
            act_id = str(act.get("address", act.get("ELI", "")))
            if act_id in saved_ids:
                continue

            raw_text = fetch_act_text(client, act)
            record = {
                "id": act_id,
                "title": act.get("title", ""),
                "year": act.get("year", year),
                "type": act.get("type", ""),
                "publisher": act.get("publisher", ""),
                "pos": act.get("pos", ""),
                "eli": act.get("ELI", ""),
                "status": act.get("status", ""),
                "promulgation": act.get("promulgation", ""),
                "has_html": act.get("textHTML", False),
                "url": f"https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id={act_id}",
                "raw_text": raw_text,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved_ids.add(act_id)
            saved += 1
            time.sleep(0.2)

    log.info("Year %d: %d acts in %s", year, saved, out_file)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Polish legal acts from ISAP API and save as JSONL."
    )
    parser.add_argument("--year", type=int, help="Single year to fetch (e.g. 2024)")
    parser.add_argument("--year-from", type=int, default=2015, help="Start year (inclusive)")
    parser.add_argument("--year-to", type=int, default=2024, help="End year (inclusive)")
    parser.add_argument(
        "--output", type=Path, default=Path("data/raw"), help="Output directory for JSONL files"
    )
    parser.add_argument(
        "--publisher",
        default=None,
        help="Publisher filter: DU (Dziennik Ustaw), MP (Monitor Polski). Default: both.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max acts per year (for testing). Default: all."
    )
    args = parser.parse_args()

    years = [args.year] if args.year else list(range(args.year_from, args.year_to + 1))

    total_acts = 0
    with httpx.Client(follow_redirects=True) as client:
        for year in years:
            n = process_year(client, year, args.output, args.publisher)
            total_acts += n

    log.info("Done. Total acts saved: %d", total_acts)


if __name__ == "__main__":
    main()
