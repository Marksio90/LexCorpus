"""
fetch_kis.py — Scraper for KIS (Krajowa Informacja Skarbowa) individual tax interpretations.

Source: eureka.mf.gov.pl REST API (public, no auth required)
Each interpretation is saved as a JSONL record compatible with preprocess.py.

Output fields: {id, title, year, publisher, pos, url, raw_text, date, tax_type, keywords}

Usage:
    python scripts/fetch_kis.py --output data/raw/
    python scripts/fetch_kis.py --year-from 2022 --year-to 2025 --output data/raw/
    python scripts/fetch_kis.py --max-items 500 --output data/raw/  # for testing
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# EUREKA public API (System Informacji Celno-Skarbowej)
EUREKA_API_BASE = os.environ.get(
    "KIS_API_URL",
    "https://eureka.mf.gov.pl",
)
SEARCH_ENDPOINT = f"{EUREKA_API_BASE}/api/public/v1/wyszukiwarka/informacje/"

PAGE_SIZE = 200
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0
REQUEST_TIMEOUT = 30.0

# Rate-limit: be polite to MF servers
DELAY_BETWEEN_REQUESTS = float(os.environ.get("KIS_DELAY", "0.3"))

# Max pages to fetch (safety limit to avoid extremely long runs)
MAX_PAGES = int(os.environ.get("KIS_MAX_PAGES", "0"))  # 0 = unlimited

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Referer": f"{EUREKA_API_BASE}/",
    "Origin": EUREKA_API_BASE,
    "Content-Type": "application/json",
}

# Columns to request from EUREKA search API
SEARCH_COLUMNS = [
    "KATEGORIA_INFORMACJI",
    "SYG",
    "DT_WYD",
    "DATA_PUBLIKACJI",
    "AUTOR",
    "ID_INFORMACJI",
    "TEZA",
    "SLOWA_KLUCZOWE",
    "PRZEPISY",
    "ZAGADNIENIA",
    "TRESC_INTERESARIUSZ",
    "STATUS_INFORMACJI",
]


def _strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities."""
    if not raw:
        return ""
    # Decode HTML entities
    text = html.unescape(raw)
    # Remove style/script tags and their content
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p> etc. with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li>", "\n- ", text, flags=re.IGNORECASE)
    # Remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Clean up whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _post_with_backoff(
    client: httpx.Client,
    url: str,
    json_body: dict,
    retries: int = MAX_RETRIES,
) -> dict | None:
    backoff = INITIAL_BACKOFF
    for attempt in range(retries):
        try:
            r = client.post(url, json=json_body, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 or r.status_code >= 500:
                log.warning("HTTP %d for %s, retry %d/%d in %.1fs",
                            r.status_code, url, attempt + 1, retries, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            else:
                log.debug("HTTP %d for %s — skipping", r.status_code, url)
                return None
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            log.warning("Request error for %s: %s — retry %d/%d", url, exc, attempt + 1, retries)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    log.error("Exhausted retries for %s", url)
    return None


def search_interpretations(
    client: httpx.Client,
    page: int,
    page_size: int = PAGE_SIZE,
    sort: str = "DATA_PUBLIKACJI,desc",
) -> dict | None:
    """
    POST /api/public/v1/wyszukiwarka/informacje/

    Returns raw API response dict with 'results' and 'totalHits'.
    """
    body = {
        "filter": {},
        "columns": SEARCH_COLUMNS,
        "searchInFullPhrase": True,
        "searchInContent": False,
        "searchInSynonyms": False,
        "searchQuery": "",
        "warunkiDodatkowe": [],
    }
    url = f"{SEARCH_ENDPOINT}?size={page_size}&page={page}&sort={sort}"
    return _post_with_backoff(client, url, body)


def _extract_year(date_str: str | None) -> str:
    """Extract year from ISO date string."""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return str(dt.year)
    except ValueError:
        # Fallback: try first 4 chars
        return date_str[:4] if len(date_str) >= 4 else ""


def _extract_tax_type(zagadnienia: list[str] | None) -> str:
    """Infer tax type from ZAGADNIENIA (topics)."""
    if not zagadnienia:
        return ""
    tax_types = []
    for z in zagadnienia:
        z_lower = z.lower()
        if "podatku od towarów i usług" in z_lower or "vat" in z_lower:
            tax_types.append("VAT")
        elif "podatku dochodowym od osób fizycznych" in z_lower or "pit" in z_lower:
            tax_types.append("PIT")
        elif "podatku dochodowym od osób prawnych" in z_lower or "cit" in z_lower:
            tax_types.append("CIT")
        elif "akcyza" in z_lower:
            tax_types.append("Akcyza")
        elif "cl" in z_lower:
            tax_types.append("Cło")
    return ", ".join(sorted(set(tax_types))) if tax_types else ""


def build_record(item: dict) -> dict | None:
    """Convert EUREKA search result into a JSONL-compatible record."""
    interp_id = str(item.get("ID_INFORMACJI", ""))
    if not interp_id:
        return None

    # Signature
    signature = item.get("SYG") or interp_id

    # Date — prefer DATA_PUBLIKACJI, fallback to DT_WYD
    date_str = item.get("DATA_PUBLIKACJI") or item.get("DT_WYD") or ""
    year = _extract_year(date_str)

    # Tax type from topics
    tax_type = _extract_tax_type(item.get("ZAGADNIENIA"))

    # Title / teza
    teza = item.get("TEZA", "")
    title = teza.strip() if teza else f"Interpretacja {signature}"

    # Raw text — clean HTML from TRESC_INTERESARIUSZ
    raw_html = item.get("TRESC_INTERESARIUSZ", "")
    raw_text = _strip_html(raw_html)

    # Skip records with no useful text
    if not raw_text or len(raw_text) < 50:
        log.warning("Skipping %s (sig=%s) — raw_text too short (%d chars)", interp_id, signature, len(raw_text))
        return None

    # Author
    autor = item.get("AUTOR", [])
    publisher = ", ".join(str(a) for a in autor) if isinstance(autor, list) else str(autor)
    if not publisher:
        publisher = "KIS"

    # Keywords
    keywords = item.get("SLOWA_KLUCZOWE", [])
    if not isinstance(keywords, list):
        keywords = []

    # Interpretation type
    kategoria = item.get("KATEGORIA_INFORMACJI", [])
    interp_type = kategoria[0] if isinstance(kategoria, list) and kategoria else "Interpretacja indywidualna"

    # URL
    url = f"{EUREKA_API_BASE}/interpretacja/{interp_id}"

    return {
        "id": f"kis_{interp_id}",
        "title": title,
        "year": year,
        "publisher": publisher,
        "pos": signature,
        "url": url,
        "raw_text": raw_text,
        "date": date_str[:10] if date_str else "",
        "tax_type": tax_type,
        "keywords": keywords,
        "interpretation_type": interp_type,
    }


def fetch_year_range(
    client: httpx.Client,
    year_from: int,
    year_to: int,
    output_dir: Path,
    max_items: int | None = None,
    delay: float = DELAY_BETWEEN_REQUESTS,
) -> int:
    """Fetch all interpretations between year_from and year_to."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"kis_{year_from}_{year_to}.jsonl"

    # Resume support: load already-saved IDs
    saved_ids: set[str] = set()
    if out_file.exists():
        with out_file.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    saved_ids.add(str(rec.get("id", "")))
                except json.JSONDecodeError:
                    pass
        log.info("Resuming — %d interpretations already saved", len(saved_ids))

    log.info("Scanning KIS interpretations via EUREKA %d-%d ...", year_from, year_to)

    saved = len(saved_ids)
    page = 0
    stop_reason = None

    with out_file.open("a", encoding="utf-8") as fout:
        while True:
            if max_items and saved >= max_items:
                stop_reason = f"max_items ({max_items}) reached"
                break

            data = search_interpretations(client, page=page, page_size=PAGE_SIZE)
            if data is None:
                stop_reason = "API error"
                break

            items = data.get("results", [])
            total_hits = data.get("totalHits", 0)

            if not items:
                stop_reason = "no more results"
                break

            if page == 0:
                log.info("Total interpretations available: %d", total_hits)

            for item in tqdm(items, desc=f"Page {page + 1}", leave=False):
                if max_items and saved >= max_items:
                    stop_reason = f"max_items ({max_items}) reached"
                    break

                record = build_record(item)
                if record is None:
                    continue

                record_id = record["id"]
                if record_id in saved_ids:
                    continue

                # Filter by year (client-side, since EUREKA public API
                # does not expose a working date filter)
                try:
                    record_year = int(record.get("year", 0))
                except ValueError:
                    record_year = 0

                if record_year and record_year < year_from:
                    # Results are sorted by DATA_PUBLIKACJI desc,
                    # so once we hit a year below year_from we can stop
                    # (but only if we're confident in the sort order)
                    stop_reason = f"year {record_year} < year_from {year_from}"
                    break

                if record_year and record_year > year_to:
                    log.debug("Skipping %s — year %s > year_to %d", record_id, record_year, year_to)
                    continue

                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                saved_ids.add(record_id)
                saved += 1

            if stop_reason:
                break

            page += 1
            time.sleep(delay)

    log.info("Done. Saved %d interpretations to %s (%s)", saved, out_file, stop_reason or "finished")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch KIS individual tax interpretations from the EUREKA portal."
    )
    parser.add_argument("--year-from", type=int, default=2020, help="Start year (inclusive)")
    parser.add_argument("--year-to", type=int, default=date.today().year, help="End year (inclusive)")
    parser.add_argument("--output", type=Path, default=Path("data/raw"), help="Output directory")
    parser.add_argument(
        "--max-items", type=int, default=None,
        help="Limit total items fetched (for testing). Default: all."
    )
    parser.add_argument(
        "--delay", type=float, default=DELAY_BETWEEN_REQUESTS,
        help=f"Delay between requests in seconds (default: {DELAY_BETWEEN_REQUESTS})"
    )
    args = parser.parse_args()

    with httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
        n = fetch_year_range(
            client,
            year_from=args.year_from,
            year_to=args.year_to,
            output_dir=args.output,
            max_items=args.max_items,
            delay=args.delay,
        )

    log.info("Total: %d interpretations fetched", n)


if __name__ == "__main__":
    main()
