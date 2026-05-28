"""
fetch_isap.py — Scraper for ISAP (Internetowy System Aktów Prawnych)

Downloads legal acts from the Sejm REST API:
  https://api.sejm.gov.pl/eli/acts

Saves each act as a line in a JSONL file under data/raw/.
Fields: {id, title, year, type, url, raw_text}

Usage:
    python scripts/fetch_isap.py --year 2023 --output data/raw/
    python scripts/fetch_isap.py --year-from 2020 --year-to 2023 --output data/raw/
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

BASE_URL = "https://api.sejm.gov.pl/eli/acts"
ACT_TEXT_URL = "https://api.sejm.gov.pl/eli/acts/{publisher}/{year}/{pos}/text"
ACT_HTML_URL = "https://isap.sejm.gov.pl/isap.nsf/download.xsp/WDU{year:04d}{pos:04d}/T/D{year:04d}{pos:04d}TK.htm"

MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0  # seconds
REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100


def fetch_with_backoff(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    retries: int = MAX_RETRIES,
) -> httpx.Response | None:
    """GET request with exponential backoff on rate-limit or server errors."""
    backoff = INITIAL_BACKOFF
    for attempt in range(retries):
        try:
            response = client.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response
            if response.status_code == 429 or response.status_code >= 500:
                log.warning(
                    "HTTP %d for %s, retry %d/%d in %.1fs",
                    response.status_code,
                    url,
                    attempt + 1,
                    retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            else:
                log.error("HTTP %d for %s — skipping", response.status_code, url)
                return None
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            log.warning("Request error for %s: %s — retry %d/%d", url, exc, attempt + 1, retries)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    log.error("Exhausted retries for %s", url)
    return None


def list_acts_for_year(client: httpx.Client, year: int) -> list[dict]:
    """Return all act metadata entries for a given year by paginating the API."""
    acts: list[dict] = []
    offset = 0

    while True:
        params = {
            "year": year,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        response = fetch_with_backoff(client, BASE_URL, params=params)
        if response is None:
            break

        try:
            data = response.json()
        except json.JSONDecodeError:
            log.error("Invalid JSON from acts list endpoint, offset=%d", offset)
            break

        # The API returns {"count": N, "items": [...]} or just a list
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", data.get("acts", []))
        else:
            items = []

        if not items:
            break

        acts.extend(items)
        log.info("  year=%d offset=%d fetched %d acts (total so far: %d)", year, offset, len(items), len(acts))

        if len(items) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.3)  # polite crawl delay

    return acts


def fetch_act_text(client: httpx.Client, act: dict) -> str:
    """Download the full text of a single act. Tries XML endpoint, falls back to HTML."""
    publisher = act.get("publisher", "WDU")
    year = act.get("year", "")
    pos = act.get("pos", act.get("number", ""))

    # Try the ELI text endpoint first
    text_url = ACT_TEXT_URL.format(publisher=publisher, year=year, pos=pos)
    response = fetch_with_backoff(client, text_url)
    if response is not None and response.text.strip():
        return response.text

    # Fallback: ISAP HTML download
    try:
        pos_int = int(pos)
        year_int = int(year)
        html_url = ACT_HTML_URL.format(year=year_int, pos=pos_int)
        response = fetch_with_backoff(client, html_url)
        if response is not None and response.text.strip():
            return response.text
    except (ValueError, TypeError):
        pass

    # Last resort: use any text field already in the metadata
    return act.get("text", act.get("content", ""))


def process_year(client: httpx.Client, year: int, output_dir: Path) -> int:
    """Fetch and save all acts for a given year. Returns number of acts saved."""
    log.info("Processing year %d …", year)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"acts_{year}.jsonl"

    # Resume support: collect already-saved IDs
    saved_ids: set[str] = set()
    if out_file.exists():
        with out_file.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    saved_ids.add(str(rec.get("id", "")))
                except json.JSONDecodeError:
                    pass
        log.info("  Resuming — %d acts already saved for %d", len(saved_ids), year)

    acts_meta = list_acts_for_year(client, year)
    if not acts_meta:
        log.warning("No acts found for year %d", year)
        return 0

    saved = len(saved_ids)
    with out_file.open("a", encoding="utf-8") as fh:
        for act in tqdm(acts_meta, desc=f"Acts {year}", unit="act"):
            act_id = str(act.get("id", act.get("ELI", act.get("pos", ""))))
            if act_id in saved_ids:
                continue

            raw_text = fetch_act_text(client, act)
            record = {
                "id": act_id,
                "title": act.get("title", act.get("name", "")),
                "year": act.get("year", year),
                "type": act.get("type", act.get("status", "")),
                "url": act.get("ELI", act.get("url", "")),
                "publisher": act.get("publisher", "WDU"),
                "pos": act.get("pos", act.get("number", "")),
                "raw_text": raw_text,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved_ids.add(act_id)
            saved += 1
            time.sleep(0.2)  # respectful rate limit

    newly_saved = saved - len(saved_ids) + len(acts_meta)
    log.info("Year %d: %d acts total in %s", year, saved, out_file)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Polish legal acts from ISAP API and save as JSONL."
    )
    parser.add_argument("--year", type=int, help="Single year to fetch (e.g. 2023)")
    parser.add_argument("--year-from", type=int, default=2000, help="Start year (inclusive)")
    parser.add_argument("--year-to", type=int, default=2024, help="End year (inclusive)")
    parser.add_argument(
        "--output", type=Path, default=Path("data/raw"), help="Output directory for JSONL files"
    )
    parser.add_argument(
        "--publisher",
        default="WDU",
        help="Publisher code: WDU (Dziennik Ustaw), WMP (Monitor Polski)",
    )
    args = parser.parse_args()

    if args.year:
        years = [args.year]
    else:
        years = list(range(args.year_from, args.year_to + 1))

    headers = {
        "Accept": "application/json",
        "User-Agent": "LexCorpus-Scraper/0.1 (Polish Legal AI research project)",
    }

    total_acts = 0
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        for year in years:
            n = process_year(client, year, args.output)
            total_acts += n

    log.info("Done. Total acts saved: %d", total_acts)


if __name__ == "__main__":
    main()
