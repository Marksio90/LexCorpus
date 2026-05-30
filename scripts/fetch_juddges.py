"""
fetch_juddges.py — Download JuDDGES Polish court judgment datasets from HuggingFace.

JuDDGES (Judicial Decisions Dataset for German, English, and Slavic Languages)
contains 437,450 Polish court judgments from orzeczenia.ms.gov.pl — much larger
than the SAOS dataset.

Homepage: https://huggingface.co/JuDDGES
Paper:    https://arxiv.org/abs/2406.07247

Converts JuDDGES JSON fields to LexCorpus SAOS-compatible JSONL format:
  {id, text_html, case_number, court_type, judgment_date, source_url,
   referenced_regulations, judges, court_name, judgment_type}

Usage:
    python scripts/fetch_juddges.py --datasets all --output data/raw/
    python scripts/fetch_juddges.py --datasets pl-court-raw --output data/raw/ --max-records 5000
    python scripts/fetch_juddges.py --datasets pl-swiss-franc-loans,pl-appealcourt-criminal
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Dataset registry ──────────────────────────────────────────────────────────

JUDDGES_DATASETS: dict[str, dict[str, Any]] = {
    "pl-court-raw": {
        "hf_id": "JuDDGES/pl-court-raw",
        "description": "437,450 Polish court judgments from orzeczenia.ms.gov.pl",
        "output": "juddges_raw.jsonl",
        "streaming": True,   # Use streaming for large dataset — don't load into RAM
        "split": "train",
        "court_type_default": "COMMON",
    },
    "pl-appealcourt-criminal": {
        "hf_id": "JuDDGES/pl-appealcourt-criminal",
        "description": "6,050 Polish appeal court criminal cases with structured annotations",
        "output": "juddges_appealcourt.jsonl",
        "streaming": False,
        "split": "train",
        "court_type_default": "COMMON",  # appeal courts are part of the common court system
    },
    "pl-swiss-franc-loans": {
        "hf_id": "JuDDGES/pl-swiss-franc-loans",
        "description": "6,265 CHF loan dispute cases (666 gold-annotated)",
        "output": "juddges_chf.jsonl",
        "streaming": False,
        "split": "train",
        "court_type_default": "COMMON",
    },
}

ALL_DATASET_KEYS = list(JUDDGES_DATASETS.keys())


# ── Field mapping ─────────────────────────────────────────────────────────────
#
# JuDDGES datasets have somewhat inconsistent field names across subsets.
# We probe for each alternative and pick the first one found.
#
# Reference schemas (checked against HF dataset viewer 2025-05):
#   pl-court-raw:           id, docket_number, judgment_date, court_id, court_name,
#                           text_legal_bases, text_judgement, judges, department_name
#   pl-appealcourt-criminal: id, signature, date, court, text, judges,
#                             legal_bases, verdict
#   pl-swiss-franc-loans:   id, signature, date, court_name, text, judges,
#                            legal_bases, verdict

def _get(record: dict, *keys: str, default: Any = None) -> Any:
    """Try multiple field names and return the first non-None value."""
    for key in keys:
        val = record.get(key)
        if val is not None:
            return val
    return default


def _extract_text(record: dict) -> str:
    """Extract the main judgment text, preferring cleaned text over HTML."""
    # pl-court-raw has separate fields for legal reasoning and judgment text
    reasoning = _get(record, "text_judgement", "text_reasoning", "reasoning")
    bases = _get(record, "text_legal_bases", "legal_bases_text")

    if reasoning and isinstance(reasoning, str) and len(reasoning) > 100:
        return (reasoning + "\n\n" + bases) if bases else reasoning

    # Generic text fields
    text = _get(record, "text", "content", "body", "judgment_text")
    if text and isinstance(text, str):
        return text

    return ""


def _extract_court_type(record: dict, default: str = "COMMON") -> str:
    """Map JuDDGES court metadata to SAOS court_type strings."""
    court_name = str(_get(record, "court_name", "court", "court_id", default="")).upper()

    if any(kw in court_name for kw in ("NSA", "WSA", "ADMINISTRATIVE", "ADMIN")):
        return "ADMINISTRATIVE"
    if any(kw in court_name for kw in ("SN", "SUPREME", "NAJWYŻSZY")):
        return "SUPREME"
    if any(kw in court_name for kw in ("TK", "KONSTYTUCYJNY", "CONSTITUTIONAL")):
        return "CONSTITUTIONAL_TRIBUNAL"
    if any(kw in court_name for kw in ("KIO", "ZAMÓWIEŃ", "APPEAL CHAMBER")):
        return "NATIONAL_APPEAL_CHAMBER"
    return default


def _extract_regulations(record: dict) -> list[dict]:
    """Extract referenced legal regulations in SAOS format."""
    raw = _get(record, "legal_bases", "text_legal_bases", "referenced_regulations")
    if raw is None:
        return []

    if isinstance(raw, list):
        result = []
        for item in raw:
            if isinstance(item, str):
                result.append({"citation": item, "title": item, "year": None,
                                "journal_no": None, "entry": None})
            elif isinstance(item, dict):
                result.append({
                    "citation": item.get("text") or item.get("citation") or "",
                    "title": item.get("journalTitle") or item.get("title") or "",
                    "year": item.get("journalYear") or item.get("year"),
                    "journal_no": item.get("journalNo"),
                    "entry": item.get("journalEntry") or item.get("entry"),
                })
        return result

    if isinstance(raw, str) and raw.strip():
        # Some datasets store as a newline-separated string
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        return [{"citation": l, "title": l, "year": None, "journal_no": None, "entry": None}
                for l in lines]

    return []


def _extract_judges(record: dict) -> list[str]:
    """Extract judge names as a list of strings."""
    raw = _get(record, "judges", "judge", "judge_name")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(j).strip() for j in raw if j]
    if isinstance(raw, str):
        # Some datasets encode as comma or semicolon separated
        return [j.strip() for j in re.split(r"[;,]", raw) if j.strip()]
    return []


def _extract_judgment_type(record: dict) -> str:
    """Extract judgment type (verdict category)."""
    raw = _get(record, "judgment_type", "verdict", "type", "decision_type")
    if raw is None:
        return ""
    return str(raw).strip()


def _convert_to_saos_format(
    record: dict,
    dataset_key: str,
    record_index: int,
) -> dict | None:
    """
    Convert a JuDDGES record to SAOS-compatible format.

    Returns None if the record should be skipped (e.g. empty text).
    """
    spec = JUDDGES_DATASETS[dataset_key]

    record_id = _get(record, "id", "uid", "judgment_id")
    if record_id is None:
        record_id = f"{dataset_key}_{record_index}"

    text = _extract_text(record)
    if not text or len(text.strip()) < 50:
        return None  # Skip records with no usable text

    case_number = str(_get(record, "docket_number", "signature", "case_number",
                           "case_id", "sygnatura", default="") or "").strip()
    judgment_date = str(_get(record, "judgment_date", "date", "decision_date",
                             "data", default="") or "").strip()

    # Normalise date format to YYYY-MM-DD
    judgment_date = _normalise_date(judgment_date)

    court_type = _extract_court_type(record, default=spec["court_type_default"])

    court_name = str(_get(record, "court_name", "court", "court_id", "department_name",
                          default="") or "").strip()

    source_url = str(_get(record, "source_url", "url", "judgment_url", "link",
                          default="") or "").strip()
    if not source_url and case_number:
        # orzeczenia.ms.gov.pl can be used as a canonical URL base
        source_url = f"https://orzeczenia.ms.gov.pl/search/?signature={case_number}"

    return {
        "id": f"juddges_{dataset_key}_{record_id}",
        "juddges_id": str(record_id),
        "dataset": dataset_key,
        "court_type": court_type,
        "court_name": court_name,
        "case_number": case_number,
        "judgment_date": judgment_date,
        "judgment_type": _extract_judgment_type(record),
        "judges": _extract_judges(record),
        "text_html": text,   # JuDDGES provides plain text, not HTML — field name kept for compatibility
        "referenced_regulations": _extract_regulations(record),
        "source_url": source_url,
        "source_code": "JUDDGES",
        "publication_date": "",
    }


def _normalise_date(raw: str) -> str:
    """Try to normalise various date formats to YYYY-MM-DD."""
    if not raw:
        return ""
    # Already correct format
    import re
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    # DD.MM.YYYY
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # YYYY/MM/DD
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Partial: just return whatever we have
    return raw[:10] if len(raw) >= 10 else raw


# Import re at module level for _normalise_date and _extract_judges
import re


# ── Download logic ────────────────────────────────────────────────────────────

def _check_datasets_library() -> None:
    """Ensure the datasets library is installed."""
    try:
        import datasets  # noqa: F401
    except ImportError:
        log.error(
            "The 'datasets' library is required: pip install datasets\n"
            "  or: pip install 'datasets[streaming]'"
        )
        sys.exit(1)


def _iter_dataset(
    hf_id: str,
    split: str,
    streaming: bool,
    max_records: int | None,
) -> Iterator[dict]:
    """Iterate over HuggingFace dataset records, optionally with streaming."""
    from datasets import load_dataset

    log.info("Loading HF dataset '%s' (split=%s, streaming=%s) …", hf_id, split, streaming)

    try:
        ds = load_dataset(hf_id, split=split, streaming=streaming, trust_remote_code=False)
    except Exception as exc:
        # Some datasets require a config name — try without split
        log.warning("load_dataset failed (%s), retrying without explicit split …", exc)
        try:
            ds = load_dataset(hf_id, streaming=streaming, trust_remote_code=False)
            # If it's a DatasetDict, pick the first available split
            from datasets import DatasetDict
            if isinstance(ds, DatasetDict):
                available = list(ds.keys())
                chosen = split if split in available else available[0]
                log.info("Using split '%s' from available: %s", chosen, available)
                ds = ds[chosen]
        except Exception as exc2:
            log.error("Failed to load dataset '%s': %s", hf_id, exc2)
            return

    count = 0
    for record in ds:
        if max_records is not None and count >= max_records:
            break
        yield dict(record)
        count += 1


def fetch_dataset(
    dataset_key: str,
    output_dir: Path,
    max_records: int | None = None,
    skip_existing: bool = True,
) -> int:
    """
    Download one JuDDGES dataset and convert to SAOS-compatible JSONL.

    Returns the number of records saved.
    """
    spec = JUDDGES_DATASETS[dataset_key]
    out_path = output_dir / spec["output"]

    # Count existing records for resume support
    existing_ids: set[str] = set()
    if skip_existing and out_path.exists():
        log.info("Output file exists — loading existing IDs for dedup …")
        try:
            with out_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        existing_ids.add(json.loads(line)["id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
            log.info("Found %d existing records in %s", len(existing_ids), out_path.name)
        except OSError:
            existing_ids = set()

    saved = 0
    skipped_empty = 0
    skipped_dup = 0
    t_start = time.monotonic()

    log.info("=== Fetching '%s' — %s ===", dataset_key, spec["description"])

    with out_path.open("a", encoding="utf-8") as out_fh:
        for i, raw_record in enumerate(_iter_dataset(
            hf_id=spec["hf_id"],
            split=spec["split"],
            streaming=spec["streaming"],
            max_records=max_records,
        )):
            record = _convert_to_saos_format(raw_record, dataset_key, i)

            if record is None:
                skipped_empty += 1
                continue

            if record["id"] in existing_ids:
                skipped_dup += 1
                continue

            out_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing_ids.add(record["id"])
            saved += 1

            if saved % 500 == 0:
                elapsed = time.monotonic() - t_start
                rate = saved / elapsed if elapsed > 0 else 0
                log.info(
                    "  [%s] Saved %d records (%.0f/s, skipped: %d empty, %d dup) …",
                    dataset_key, saved, rate, skipped_empty, skipped_dup,
                )

    elapsed = time.monotonic() - t_start
    log.info(
        "=== '%s' done: %d saved, %d empty skipped, %d dup skipped (%.1fs) → %s ===",
        dataset_key, saved, skipped_empty, skipped_dup, elapsed, out_path,
    )
    return saved


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download JuDDGES Polish court judgment datasets from HuggingFace.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--datasets",
        default="all",
        help=(
            "Comma-separated list of datasets to download, or 'all'. "
            f"Available: {', '.join(ALL_DATASET_KEYS)}"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw"),
        help="Output directory for JSONL files",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Maximum records per dataset (useful for testing — omit for full download)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        default=False,
        help="Re-download records even if the output file already exists (overwrites)",
    )
    args = parser.parse_args()

    _check_datasets_library()

    if args.datasets.strip().lower() == "all":
        selected = ALL_DATASET_KEYS
    else:
        selected = [k.strip() for k in args.datasets.split(",") if k.strip()]
        unknown = set(selected) - set(JUDDGES_DATASETS)
        if unknown:
            log.error("Unknown dataset(s): %s. Available: %s", unknown, ALL_DATASET_KEYS)
            sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)

    log.info("Fetching %d JuDDGES dataset(s): %s", len(selected), selected)
    if args.max_records:
        log.info("Limited to %d records per dataset (--max-records)", args.max_records)

    total_saved = 0
    for dataset_key in selected:
        n = fetch_dataset(
            dataset_key=dataset_key,
            output_dir=args.output,
            max_records=args.max_records,
            skip_existing=not args.no_skip_existing,
        )
        total_saved += n

    log.info("All done. Total new records saved: %d", total_saved)
    log.info(
        "To preprocess and ingest into Qdrant:\n"
        "  python scripts/preprocess.py --input %s --output data/processed/\n"
        "  python rag/ingest.py --input data/processed/chunks.jsonl --qdrant data/qdrant",
        args.output,
    )


if __name__ == "__main__":
    main()
