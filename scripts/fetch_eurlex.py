"""
fetch_eurlex.py — Pobiera rozporządzenia i dyrektywy UE z EUR-Lex (CELLAR SPARQL + REST).

Używa:
  - CELLAR SPARQL endpoint (publications.europa.eu) do pobrania listy aktów
  - EUR-Lex REST do pobrania tekstu HTML w języku polskim

Zapisuje do data/raw/eurlex_<year>.jsonl — kompatybilne z preprocess.py.
Pola: {id, title, year, type, publisher, pos, url, raw_text}

Usage:
    python scripts/fetch_eurlex.py --year-from 2020 --year-to 2025 --output data/raw/
    python scripts/fetch_eurlex.py --type regulation --max-acts 500
    python scripts/fetch_eurlex.py --type regulation,directive --year-from 2023
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
EURLEX_HTML_URL = "https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}"
EURLEX_ACT_URL = "https://eur-lex.europa.eu/legal-content/{lang}/ALL/?uri=CELEX:{celex}"

REQUEST_TIMEOUT = 45.0
MAX_RETRIES = 5
INITIAL_BACKOFF = 3.0

# act type → CDM class name in CELLAR ontology
ACT_TYPE_MAP = {
    "regulation": "regulation",
    "directive": "directive",
    "decision": "decision",
}

# Human-readable publisher tags stored in JSONL
PUBLISHER_TAG = "EURLEX"

HEADERS = {
    "User-Agent": (
        "LexCorpus/1.0 (legal research platform; contact: admin@lexcorpus.pl) "
        "Mozilla/5.0 (compatible)"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

# ──────────────────────────────────────────────────────────────────────────────
# SPARQL helpers
# ──────────────────────────────────────────────────────────────────────────────

SPARQL_QUERY_TEMPLATE = """\
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?celex ?title ?date ?type
WHERE {{
  ?work a cdm:{cdm_type} ;
        cdm:work_date_document ?date ;
        cdm:resource_legal_id_celex ?celex .
  OPTIONAL {{
    ?work cdm:work_title ?title .
    FILTER(LANG(?title) = "pl")
  }}
  FILTER(?date >= "{year_from}-01-01"^^xsd:date &&
         ?date <= "{year_to}-12-31"^^xsd:date)
  BIND("{act_type}" AS ?type)
}}
ORDER BY DESC(?date)
LIMIT {limit}
OFFSET {offset}
"""

SPARQL_PAGE_SIZE = 200


def _sparql_query(query: str) -> list[dict]:
    """Execute a SPARQL query and return the bindings list."""
    params = urllib.parse.urlencode(
        {"query": query, "format": "application/sparql-results+json"}
    )
    url = f"{SPARQL_ENDPOINT}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": HEADERS["User-Agent"],
        },
    )
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data.get("results", {}).get("bindings", [])
        except urllib.error.HTTPError as exc:
            log.warning("SPARQL HTTP %d (attempt %d/%d)", exc.code, attempt + 1, MAX_RETRIES)
        except Exception as exc:
            log.warning("SPARQL error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, exc)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60.0)
    log.error("SPARQL query exhausted retries")
    return []


def query_acts(
    act_type: str,
    year_from: int,
    year_to: int,
    max_acts: int,
) -> list[dict]:
    """
    Query CELLAR SPARQL for a list of acts of the given type and year range.
    Returns list of dicts with keys: celex, title, date, type.
    """
    cdm_type = ACT_TYPE_MAP.get(act_type, act_type)
    results: list[dict] = []
    offset = 0

    log.info("Querying CELLAR SPARQL: type=%s, %d–%d …", act_type, year_from, year_to)

    while True:
        limit = min(SPARQL_PAGE_SIZE, max_acts - len(results))
        if limit <= 0:
            break

        query = SPARQL_QUERY_TEMPLATE.format(
            cdm_type=cdm_type,
            year_from=year_from,
            year_to=year_to,
            act_type=act_type,
            limit=limit,
            offset=offset,
        )

        bindings = _sparql_query(query)
        if not bindings:
            break

        for b in bindings:
            celex = b.get("celex", {}).get("value", "")
            title = b.get("title", {}).get("value", "")
            date = b.get("date", {}).get("value", "")[:10]  # YYYY-MM-DD
            act_type_val = b.get("type", {}).get("value", act_type)
            if celex:
                results.append(
                    {
                        "celex": celex,
                        "title": title,
                        "date": date,
                        "type": act_type_val,
                    }
                )

        log.info(
            "  type=%s offset=%d fetched %d (total so far: %d)",
            act_type, offset, len(bindings), len(results),
        )

        if len(bindings) < limit:
            # Last page
            break

        offset += len(bindings)
        time.sleep(1.0)  # be polite to the SPARQL endpoint

    return results


# ──────────────────────────────────────────────────────────────────────────────
# HTML text fetching
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_with_backoff(client: httpx.Client, url: str) -> httpx.Response | None:
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES):
        try:
            response = client.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response
            if response.status_code in (429, 503, 502):
                log.warning(
                    "HTTP %d for %s — retry %d/%d in %.1fs",
                    response.status_code, url, attempt + 1, MAX_RETRIES, backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 120.0)
            elif response.status_code == 404:
                log.debug("HTTP 404 for %s — not available in Polish", url)
                return None
            else:
                log.debug("HTTP %d for %s — skipping", response.status_code, url)
                return None
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            log.warning(
                "Request error for %s: %s — retry %d/%d", url, exc, attempt + 1, MAX_RETRIES
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 120.0)
    log.error("Exhausted retries for %s", url)
    return None


def fetch_act_text(client: httpx.Client, celex: str, lang: str = "PL") -> str:
    """Fetch the full HTML text of an act from EUR-Lex (Polish version)."""
    url = EURLEX_HTML_URL.format(lang=lang, celex=celex)
    response = _fetch_with_backoff(client, url)
    if response is None:
        # Fallback: try English if Polish not available
        if lang != "EN":
            log.debug("Polish text not found for %s — trying English", celex)
            url_en = EURLEX_HTML_URL.format(lang="EN", celex=celex)
            response = _fetch_with_backoff(client, url_en)
    if response is None:
        return ""
    return response.text


def fetch_act_title_fallback(client: httpx.Client, celex: str, lang: str = "PL") -> str:
    """
    When SPARQL doesn't return a Polish title, fetch the act page and extract it
    from the <title> tag as a best-effort fallback.
    """
    url = EURLEX_ACT_URL.format(lang=lang, celex=celex)
    response = _fetch_with_backoff(client, url)
    if response is None:
        return ""
    try:
        soup = BeautifulSoup(response.text, "lxml")
        tag = soup.find("title")
        if tag:
            return tag.get_text(strip=True).split(" - EUR-Lex")[0].strip()
    except Exception:
        pass
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def process_acts(
    client: httpx.Client,
    acts_meta: list[dict],
    output_file: Path,
    lang: str,
    delay: float,
) -> int:
    """
    Fetch HTML text for each act and append to output_file.
    Skips acts already present in the file (resume support).
    Returns number of newly saved acts.
    """
    # Load already-saved IDs for resume
    saved_ids: set[str] = set()
    if output_file.exists():
        with output_file.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    saved_ids.add(str(rec.get("id", "")))
                except json.JSONDecodeError:
                    pass
        log.info("Resuming — %d acts already in %s", len(saved_ids), output_file.name)

    saved = 0
    lang_upper = lang.upper()

    with output_file.open("a", encoding="utf-8") as fh:
        for act in tqdm(acts_meta, desc=f"Fetching {output_file.name}", unit="act"):
            celex = act["celex"]
            if celex in saved_ids:
                continue

            # Fetch HTML text
            raw_text = fetch_act_text(client, celex, lang_upper)

            # If title missing from SPARQL, try fetching from EUR-Lex page
            title = act["title"]
            if not title and raw_text:
                try:
                    soup = BeautifulSoup(raw_text, "lxml")
                    h1 = soup.find("p", class_="doc-ti") or soup.find("h1")
                    if h1:
                        title = h1.get_text(separator=" ", strip=True)
                except Exception:
                    pass
            if not title:
                title = fetch_act_title_fallback(client, celex, lang_upper)

            date_str = act.get("date", "")
            year = date_str[:4] if date_str else ""

            record = {
                "id": celex,
                "title": title,
                "year": year,
                "type": act.get("type", ""),
                "publisher": PUBLISHER_TAG,
                "pos": celex,
                "url": EURLEX_HTML_URL.format(lang=lang_upper, celex=celex),
                "raw_text": raw_text,
            }

            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved_ids.add(celex)
            saved += 1
            time.sleep(delay)

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch EU regulations and directives from EUR-Lex (CELLAR SPARQL + REST) "
            "and save as JSONL compatible with preprocess.py."
        )
    )
    parser.add_argument(
        "--year-from", type=int, default=2020, help="Start year (inclusive, default: 2020)"
    )
    parser.add_argument(
        "--year-to", type=int, default=2025, help="End year (inclusive, default: 2025)"
    )
    parser.add_argument(
        "--type",
        default="regulation,directive",
        help=(
            "Comma-separated act types to fetch: regulation, directive, decision "
            "(default: regulation,directive)"
        ),
    )
    parser.add_argument(
        "--lang",
        default="PL",
        help="Language code for fetching full text (default: PL — Polish)",
    )
    parser.add_argument(
        "--max-acts",
        type=int,
        default=2000,
        help="Maximum number of acts per type (default: 2000)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="Output directory for JSONL files (default: data/raw)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between text fetch requests (default: 1.0)",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    act_types = [t.strip().lower() for t in args.type.split(",") if t.strip()]
    invalid = [t for t in act_types if t not in ACT_TYPE_MAP]
    if invalid:
        log.error(
            "Unknown act type(s): %s. Valid choices: %s",
            invalid,
            list(ACT_TYPE_MAP.keys()),
        )
        sys.exit(1)

    total_saved = 0

    with httpx.Client(follow_redirects=True) as client:
        for act_type in act_types:
            acts_meta = query_acts(
                act_type=act_type,
                year_from=args.year_from,
                year_to=args.year_to,
                max_acts=args.max_acts,
            )

            if not acts_meta:
                log.warning("No acts found for type=%s", act_type)
                continue

            log.info("Found %d %s acts — fetching texts …", len(acts_meta), act_type)

            out_file = args.output / f"eurlex_{act_type}_{args.year_from}_{args.year_to}.jsonl"
            saved = process_acts(
                client=client,
                acts_meta=acts_meta,
                output_file=out_file,
                lang=args.lang,
                delay=args.delay,
            )
            log.info("Saved %d new %s acts → %s", saved, act_type, out_file)
            total_saved += saved

    log.info("Done. Total new EUR-Lex acts saved: %d", total_saved)


if __name__ == "__main__":
    main()
