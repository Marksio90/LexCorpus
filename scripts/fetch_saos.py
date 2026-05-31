"""
fetch_saos.py — Bulk downloader for SAOS (System Analizy Orzeczeń Sądowych)

Downloads Polish court decisions from the SAOS public API (no auth required):
  https://www.saos.org.pl/api/dump/judgments

Covers: common courts, Supreme Court (SN), administrative courts (NSA/WSA),
        Constitutional Tribunal (TK), National Appeal Chamber (KIO)

Saves each judgment as a JSONL line under data/raw/saos_YYYY.jsonl
Fields: {id, court_type, case_number, judgment_date, court_name, text_html,
         referenced_regulations, source_url}

Usage:
    python scripts/fetch_saos.py --year 2024
    python scripts/fetch_saos.py --year-from 2023 --year-to 2024
    python scripts/fetch_saos.py --year 2024 --court-type SUPREME
    python scripts/fetch_saos.py --since-date 2025-01-01   # incremental sync
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

API_BASE = "https://www.saos.org.pl/api"
DUMP_URL = f"{API_BASE}/dump/judgments"

COURT_TYPES = ["COMMON", "SUPREME", "ADMINISTRATIVE", "CONSTITUTIONAL_TRIBUNAL", "NATIONAL_APPEAL_CHAMBER"]

PAGE_SIZE = 100
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0

HEADERS = {
    "User-Agent": "LexCorpus/1.0 (legal research; contact: admin@lexcorpus.pl)",
    "Accept": "application/json",
}


def fetch_page(client: httpx.Client, url: str, params: dict | None = None) -> dict | None:
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            response = client.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                log.warning("Rate limited — sleeping %ds", backoff * 2)
                time.sleep(backoff * 2)
            else:
                log.warning("HTTP %d for %s (attempt %d)", response.status_code, url, attempt + 1)
                time.sleep(backoff)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            log.warning("Request error (attempt %d): %s", attempt + 1, exc)
            time.sleep(backoff)
        backoff = min(backoff * 2, 60)
    log.error("Failed after %d attempts: %s", MAX_RETRIES, url)
    return None


def extract_judgment(item: dict) -> dict:
    """Normalise a SAOS judgment item into our storage format."""
    cases = item.get("courtCases") or []
    case_number = cases[0]["caseNumber"] if cases else ""

    judges = item.get("judges") or []
    judge_names = [j.get("name", "") for j in judges if j.get("name")]

    regs = item.get("referencedRegulations") or []
    regulations = [
        {
            "title": r.get("journalTitle", ""),
            "year": r.get("journalYear"),
            "journal_no": r.get("journalNo"),
            "entry": r.get("journalEntry"),
            "citation": r.get("text", ""),
        }
        for r in regs
    ]

    source = item.get("source") or {}

    return {
        "id": f"saos_{item['id']}",
        "saos_id": item["id"],
        "court_type": item.get("courtType", ""),
        "case_number": case_number,
        "judgment_date": item.get("judgmentDate", ""),
        "judgment_type": item.get("judgmentType", ""),
        "judges": judge_names,
        "text_html": item.get("textContent", ""),
        "referenced_regulations": regulations,
        "keywords": item.get("keywords") or [],
        "source_url": source.get("judgmentUrl", ""),
        "source_code": source.get("code", ""),
        "publication_date": source.get("publicationDate", ""),
    }


def fetch_judgments(
    client: httpx.Client,
    output_file: Path,
    date_from: str,
    date_to: str,
    court_type: str | None = None,
    since_modification: str | None = None,
) -> int:
    """Fetch all judgments for a date range and append to output_file."""
    saved_ids: set[int] = set()
    if output_file.exists():
        with output_file.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    saved_ids.add(json.loads(line)["saos_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
        log.info("Found %d existing records in %s", len(saved_ids), output_file.name)

    params: dict = {
        "pageSize": PAGE_SIZE,
        "pageNumber": 0,
        "judgmentStartDate": date_from,
        "judgmentEndDate": date_to,
    }
    if since_modification:
        params["sinceModificationDate"] = since_modification
    if court_type:
        params["courtType"] = court_type

    total_saved = 0
    page = 0

    with output_file.open("a", encoding="utf-8") as fh:
        with tqdm(desc=f"Fetching {date_from}→{date_to}", unit=" judgments") as pbar:
            next_url: str | None = DUMP_URL

            while next_url:
                if next_url == DUMP_URL:
                    data = fetch_page(client, next_url, params)
                else:
                    # Follow next link (already has all params baked in)
                    data = fetch_page(client, next_url)

                if data is None:
                    log.error("Fetch failed at page %d — stopping", page)
                    break

                items = data.get("items") or []
                for item in items:
                    saos_id = item.get("id")
                    if saos_id in saved_ids:
                        continue
                    record = extract_judgment(item)
                    if not record["text_html"]:
                        continue  # skip empty judgments
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    saved_ids.add(saos_id)
                    total_saved += 1

                pbar.update(len(items))
                page += 1

                # Find next page link
                links = data.get("links") or []
                next_url = next((lnk["href"] for lnk in links if lnk.get("rel") == "next"), None)

                time.sleep(0.2)  # be polite to SAOS

    log.info("Saved %d new judgments to %s", total_saved, output_file)
    return total_saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Polish court decisions from SAOS API.")
    parser.add_argument("--year", type=int, help="Single year to fetch (e.g. 2024)")
    parser.add_argument("--year-from", type=int, default=2020, help="Start year")
    parser.add_argument("--year-to", type=int, default=2024, help="End year")
    parser.add_argument("--since-date", help="Incremental: fetch only modified since date (YYYY-MM-DD)")
    parser.add_argument("--court-type", choices=COURT_TYPES, default=None, help="Filter by court type")
    parser.add_argument("--output", type=Path, default=Path("data/raw"), help="Output directory")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    years = [args.year] if args.year else list(range(args.year_from, args.year_to + 1))

    total = 0
    with httpx.Client() as client:
        for year in years:
            suffix = f"_{args.court_type.lower()}" if args.court_type else ""
            out_file = args.output / f"saos_{year}{suffix}.jsonl"

            log.info("=== Year %d → %s ===", year, out_file)
            n = fetch_judgments(
                client=client,
                output_file=out_file,
                date_from=f"{year}-01-01",
                date_to=f"{year}-12-31",
                court_type=args.court_type,
                since_modification=args.since_date if args.since_date else None,
            )
            total += n

    log.info("Done. Total new judgments: %d", total)


if __name__ == "__main__":
    main()
