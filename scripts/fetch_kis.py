"""
fetch_kis.py — Scraper for KIS (Krajowa Informacja Skarbowa) individual tax interpretations.

Source: interpretacje.podatki.gov.pl REST API (public, no auth required)
Each interpretation is saved as a JSONL record compatible with preprocess.py.

Output fields: {id, title, year, publisher, pos, url, raw_text, date, tax_type, keywords}

Usage:
    python scripts/fetch_kis.py --output data/raw/
    python scripts/fetch_kis.py --year-from 2022 --year-to 2025 --output data/raw/
    python scripts/fetch_kis.py --max-items 500 --output data/raw/  # for testing
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# Official KIS interpretations REST API (Ministry of Finance portal)
KIS_API_BASE = os.environ.get(
    "KIS_API_URL",
    "https://interpretacje.podatki.gov.pl",
)
SEARCH_ENDPOINT = f"{KIS_API_BASE}/api/interpretacja/szukaj"
DETAIL_ENDPOINT = f"{KIS_API_BASE}/api/interpretacja"

PAGE_SIZE = 20
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0
REQUEST_TIMEOUT = 30.0

# Rate-limit: MF portal has a soft limit
DELAY_BETWEEN_REQUESTS = float(os.environ.get("KIS_DELAY", "0.5"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Referer": f"{KIS_API_BASE}/",
    "Origin": KIS_API_BASE,
}


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


def _get_with_backoff(
    client: httpx.Client,
    url: str,
    retries: int = MAX_RETRIES,
) -> dict | None:
    backoff = INITIAL_BACKOFF
    for attempt in range(retries):
        try:
            r = client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
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
    date_from: str,
    date_to: str,
    page: int,
    interpretation_types: list[str] | None = None,
) -> tuple[list[dict], int]:
    """
    POST /api/interpretacja/szukaj

    Returns (items, total_count).
    """
    body = {
        "fraza": "",
        "strona": page,
        "rozmiarStrony": PAGE_SIZE,
        "dataDokumentuOd": date_from,
        "dataDokumentuDo": date_to,
        "sortowanie": "dataDokumentu,desc",
        "typyInterpretacji": interpretation_types or ["II"],  # II = interpretacja indywidualna
    }
    data = _post_with_backoff(client, SEARCH_ENDPOINT, body)
    if data is None:
        return [], 0

    # API may return a dict with 'items' and 'totalElements' or similar
    if isinstance(data, dict):
        items = data.get("interpretacje", data.get("items", data.get("content", [])))
        total = int(data.get("total", data.get("totalElements", data.get("totalCount", 0))))
    elif isinstance(data, list):
        items = data
        total = len(data)
    else:
        return [], 0

    return items, total


def fetch_interpretation_detail(client: httpx.Client, interp_id: str) -> dict | None:
    """GET /api/interpretacja/{id} — full content including text."""
    url = f"{DETAIL_ENDPOINT}/{interp_id}"
    return _get_with_backoff(client, url)


def _build_raw_text(detail: dict) -> str:
    """Assemble plain text from interpretation detail fields."""
    parts: list[str] = []

    # Subject / description
    temat = detail.get("temat") or detail.get("opis") or detail.get("tytul") or ""
    if temat:
        parts.append(temat.strip())

    # Main content (może być w różnych polach zależnie od wersji API)
    for field in ("tresc", "trescInterpretacji", "content", "tekst", "tekstInterpretacji"):
        val = detail.get(field)
        if val and isinstance(val, str) and val.strip():
            parts.append(val.strip())
            break

    # Justification
    for field in ("uzasadnienie", "uzasadnieniePrawne", "justification"):
        val = detail.get(field)
        if val and isinstance(val, str) and val.strip():
            parts.append("UZASADNIENIE:\n" + val.strip())
            break

    return "\n\n".join(parts) if parts else ""


def _extract_keywords(detail: dict) -> list[str]:
    kw: list[str] = []
    for field in ("slowanKluczowe", "keywords", "tagi", "tematOgolny"):
        v = detail.get(field)
        if isinstance(v, list):
            kw.extend(str(x) for x in v if x)
        elif isinstance(v, str) and v:
            kw.append(v)
    return kw


def build_record(item: dict, detail: dict | None) -> dict:
    """Merge search-result item with full detail into a JSONL-compatible record."""
    merged = {**item, **(detail or {})}

    # Signature (e.g. "0111-KDIB2-1.4010.559.2023.2.AR")
    signature = (
        merged.get("sygnatura")
        or merged.get("signature")
        or merged.get("numerInterpretacji")
        or str(merged.get("id", ""))
    )

    date_str = (
        merged.get("dataDokumentu")
        or merged.get("dataWydania")
        or merged.get("date")
        or ""
    )
    year = date_str[:4] if date_str else ""

    tax_type = (
        merged.get("rodzajPodatku")
        or merged.get("podatek")
        or merged.get("taxType")
        or ""
    )
    if isinstance(tax_type, list):
        tax_type = ", ".join(str(t) for t in tax_type)

    title_parts = []
    temat = merged.get("temat") or merged.get("opis") or merged.get("subject") or ""
    if temat:
        title_parts.append(str(temat)[:200])
    if tax_type:
        title_parts.append(f"[{tax_type}]")
    title = " — ".join(title_parts) if title_parts else f"Interpretacja {signature}"

    interp_id = str(merged.get("id", signature))
    url = (
        merged.get("url")
        or merged.get("link")
        or f"{KIS_API_BASE}/wyszukiwarka-interpretacji/{interp_id}"
    )

    raw_text = _build_raw_text(merged)

    return {
        "id": f"kis_{interp_id}",
        "title": title,
        "year": year,
        "publisher": "KIS",
        "pos": signature,
        "url": url,
        "raw_text": raw_text,
        "date": date_str,
        "tax_type": tax_type,
        "keywords": _extract_keywords(merged),
        "interpretation_type": merged.get("typInterpretacji", "II"),
    }


def fetch_year_range(
    client: httpx.Client,
    year_from: int,
    year_to: int,
    output_dir: Path,
    max_items: int | None = None,
    interpretation_types: list[str] | None = None,
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

    date_from = f"{year_from}-01-01"
    date_to = f"{year_to}-12-31"

    log.info("Scanning KIS interpretations %s → %s …", date_from, date_to)

    # Discover total count on page 0
    first_page, total = search_interpretations(
        client, date_from, date_to, page=0,
        interpretation_types=interpretation_types,
    )
    if total == 0 and not first_page:
        log.warning("No interpretations found for %s–%s (check API endpoint)", date_from, date_to)
        return 0

    if max_items:
        total = min(total, max_items)
    log.info("Total interpretations to fetch: %d", total)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    saved = len(saved_ids)

    with out_file.open("a", encoding="utf-8") as fout:
        # Process first page already fetched
        for page_idx in range(total_pages):
            if page_idx == 0:
                items = first_page
            else:
                items, _ = search_interpretations(
                    client, date_from, date_to, page=page_idx,
                    interpretation_types=interpretation_types,
                )
                time.sleep(DELAY_BETWEEN_REQUESTS)

            for item in tqdm(items, desc=f"Page {page_idx + 1}/{total_pages}", leave=False):
                if max_items and saved >= max_items:
                    break

                interp_id = str(item.get("id", item.get("sygnatura", "")))
                record_id = f"kis_{interp_id}"

                if record_id in saved_ids:
                    continue

                # Fetch full detail
                detail = None
                if interp_id:
                    detail = fetch_interpretation_detail(client, interp_id)
                    time.sleep(DELAY_BETWEEN_REQUESTS)

                record = build_record(item, detail)

                # Skip records with no useful text
                if not record.get("raw_text"):
                    log.debug("Skipping %s — no raw_text", interp_id)
                    continue

                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                saved_ids.add(record_id)
                saved += 1

            if max_items and saved >= max_items:
                break

    log.info("Done. Saved %d interpretations to %s", saved, out_file)
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch KIS individual tax interpretations from the MF portal."
    )
    parser.add_argument("--year-from", type=int, default=2020, help="Start year (inclusive)")
    parser.add_argument("--year-to", type=int, default=date.today().year, help="End year (inclusive)")
    parser.add_argument("--output", type=Path, default=Path("data/raw"), help="Output directory")
    parser.add_argument(
        "--max-items", type=int, default=None,
        help="Limit total items fetched (for testing). Default: all."
    )
    parser.add_argument(
        "--types", default="II",
        help="Comma-separated interpretation types: II=indywidualna, OI=ogólna. Default: II"
    )
    parser.add_argument(
        "--delay", type=float, default=DELAY_BETWEEN_REQUESTS,
        help=f"Delay between requests in seconds (default: {DELAY_BETWEEN_REQUESTS})"
    )
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",") if t.strip()]

    with httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
        n = fetch_year_range(
            client,
            year_from=args.year_from,
            year_to=args.year_to,
            output_dir=args.output,
            max_items=args.max_items,
            interpretation_types=types,
        )

    log.info("Total: %d interpretations fetched", n)


if __name__ == "__main__":
    main()
