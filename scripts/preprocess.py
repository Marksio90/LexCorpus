"""
preprocess.py — Clean HTML/XML legal text and split into overlapping chunks.

Reads JSONL files from data/raw/, strips markup, removes boilerplate headers/footers,
splits into ~512-token chunks with 64-token overlap, and writes chunks to data/processed/.

Output chunk fields: {act_id, title, year, chunk_index, text}

Usage:
    python scripts/preprocess.py --input data/raw/ --output data/processed/
    python scripts/preprocess.py --input data/raw/acts_2023.jsonl --output data/processed/
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

CHUNK_TOKENS = 512
OVERLAP_TOKENS = 64

# Boilerplate patterns common in Polish legal documents
BOILERPLATE_PATTERNS = [
    re.compile(r"Dziennik Ustaw\s+–\s+\d+\s+–\s+Poz\.\s+\d+", re.IGNORECASE),
    re.compile(r"Monitor Polski\s+–\s+\d+\s+–\s+Poz\.\s+\d+", re.IGNORECASE),
    re.compile(r"DZIENNIK USTAW RZECZYPOSPOLITEJ POLSKIEJ", re.IGNORECASE),
    re.compile(r"Warszawa,\s+dnia\s+\d+\s+\w+\s+\d{4}\s+r\.", re.IGNORECASE),
    re.compile(r"©\s*Kancelaria\s+Sejmu", re.IGNORECASE),
    re.compile(r"Opracowano\s+na\s+podstawie.*?(?=\n|$)", re.IGNORECASE),
    re.compile(r"-\s*\d+\s*-"),  # page numbers like "- 5 -"
    re.compile(r"_{5,}"),  # long underscores used as dividers
    re.compile(r"\f"),  # form feed / page break characters
]

# Approximate: average Polish legal word ~ 6 chars; 1 token ~ 4 chars (subword)
CHARS_PER_TOKEN = 4


def strip_markup(raw_text: str) -> str:
    """Remove HTML/XML tags and decode entities, returning plain text."""
    if not raw_text:
        return ""

    raw_stripped = raw_text.strip()

    # Detect whether content looks like XML/HTML
    if raw_stripped.startswith("<"):
        try:
            soup = BeautifulSoup(raw_text, "lxml-xml")
            text = soup.get_text(separator="\n")
        except Exception:
            try:
                soup = BeautifulSoup(raw_text, "lxml")
                text = soup.get_text(separator="\n")
            except Exception:
                # Last resort: regex strip
                text = re.sub(r"<[^>]+>", " ", raw_text)
    else:
        text = raw_text

    return text


def normalize_whitespace(text: str) -> str:
    """Collapse excess whitespace, normalize unicode, remove zero-width chars."""
    # Normalize unicode (NFC)
    text = unicodedata.normalize("NFC", text)
    # Remove zero-width and control characters
    text = re.sub(r"[​‌‍﻿\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Replace multiple spaces/tabs with single space
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse more than 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_boilerplate(text: str) -> str:
    """Remove common legal document headers, footers, and page markers."""
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)
    return text


def clean_text(raw_text: str) -> str:
    """Full cleaning pipeline: strip markup → remove boilerplate → normalize."""
    text = strip_markup(raw_text)
    text = remove_boilerplate(text)
    text = normalize_whitespace(text)
    return text


def naive_token_count(text: str) -> int:
    """Estimate token count based on character length (avoids tokenizer dependency)."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def split_into_chunks(text: str, chunk_tokens: int = CHUNK_TOKENS, overlap_tokens: int = OVERLAP_TOKENS) -> list[str]:
    """
    Split text into overlapping chunks of approximately `chunk_tokens` tokens.

    Strategy:
    1. Split on paragraph boundaries (double newlines) first.
    2. If a paragraph is too large, split on sentence boundaries.
    3. Accumulate paragraphs into chunks; when a chunk is full, start a new one
       with the last `overlap_tokens` worth of text carried over.
    """
    chunk_chars = chunk_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    # Split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

    # Further split very long paragraphs at sentence boundaries
    sentences: list[str] = []
    sentence_boundary = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])")
    for para in paragraphs:
        if len(para) > chunk_chars:
            parts = sentence_boundary.split(para)
            sentences.extend(parts)
        else:
            sentences.append(para)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence)
        if current_len + sentence_len > chunk_chars and current_parts:
            chunk_text = " ".join(current_parts)
            chunks.append(chunk_text)

            # Build overlap: keep trailing text up to overlap_chars
            overlap_text = chunk_text[-overlap_chars:] if len(chunk_text) > overlap_chars else chunk_text
            # Find a clean word boundary for the overlap start
            space_pos = overlap_text.find(" ")
            if space_pos > 0:
                overlap_text = overlap_text[space_pos + 1:]

            current_parts = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)

        current_parts.append(sentence)
        current_len += sentence_len + 1  # +1 for the space separator

    # Flush remaining
    if current_parts:
        chunks.append(" ".join(current_parts))

    # Filter out chunks that are too short to be meaningful (< 50 chars)
    return [c for c in chunks if len(c) >= 50]


def process_record(record: dict) -> list[dict]:
    """Clean and chunk a single JSONL record, returning a list of chunk dicts."""
    act_id = str(record.get("id", ""))
    title = record.get("title", "")
    year = record.get("year", "")
    raw_text = record.get("raw_text", "")

    cleaned = clean_text(raw_text)
    if not cleaned:
        return []

    chunks = split_into_chunks(cleaned)
    return [
        {
            "act_id": act_id,
            "title": title,
            "year": year,
            "publisher": record.get("publisher", "WDU"),
            "pos": record.get("pos", ""),
            "url": record.get("url", ""),
            "chunk_index": idx,
            "total_chunks": len(chunks),
            "text": chunk,
            "approx_tokens": naive_token_count(chunk),
        }
        for idx, chunk in enumerate(chunks)
    ]


def process_file(input_path: Path, output_path: Path) -> tuple[int, int]:
    """Process a single JSONL file. Returns (acts_processed, chunks_written)."""
    acts = 0
    chunks_written = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open(encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
        for line in tqdm(fin, desc=f"Processing {input_path.name}", unit="act"):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                log.warning("Skipping invalid JSON line in %s", input_path)
                continue

            chunk_records = process_record(record)
            for chunk in chunk_records:
                fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                chunks_written += 1
            acts += 1

    return acts, chunks_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and chunk Polish legal act JSONL files.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw"),
        help="Input JSONL file or directory containing JSONL files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed"),
        help="Output directory for chunked JSONL files",
    )
    parser.add_argument("--chunk-tokens", type=int, default=CHUNK_TOKENS, help="Target tokens per chunk")
    parser.add_argument("--overlap-tokens", type=int, default=OVERLAP_TOKENS, help="Overlap tokens between chunks")
    args = parser.parse_args()

    global CHUNK_TOKENS, OVERLAP_TOKENS
    CHUNK_TOKENS = args.chunk_tokens
    OVERLAP_TOKENS = args.overlap_tokens

    input_path: Path = args.input
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(input_path.glob("*.jsonl"))
    else:
        log.error("Input path does not exist: %s", input_path)
        sys.exit(1)

    if not files:
        log.error("No JSONL files found in %s", input_path)
        sys.exit(1)

    total_acts = 0
    total_chunks = 0

    for f in files:
        out_file = output_dir / f"chunks_{f.stem}.jsonl"
        acts, chunks = process_file(f, out_file)
        total_acts += acts
        total_chunks += chunks
        log.info("  %s → %s (%d acts, %d chunks)", f.name, out_file.name, acts, chunks)

    # Write a merged file for convenience
    merged_path = output_dir / "chunks.jsonl"
    with merged_path.open("w", encoding="utf-8") as fout:
        for f in sorted(output_dir.glob("chunks_acts_*.jsonl")):
            with f.open(encoding="utf-8") as fin:
                for line in fin:
                    fout.write(line)

    log.info("Done. Total: %d acts, %d chunks → %s", total_acts, total_chunks, merged_path)


if __name__ == "__main__":
    main()
