"""
build_dataset.py — Build a HuggingFace Dataset from preprocessed legal chunks.

Creates two dataset types:
  1. Instruction-tuning dataset: {"instruction", "input", "output"} — for fine-tuning.
  2. QA dataset: question–answer pairs derived from article headings.

Splits into train (80%) / val (10%) / test (10%) and saves to data/dataset/.

Usage:
    python scripts/build_dataset.py --input data/processed/chunks.jsonl --output data/dataset/
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from pathlib import Path

from datasets import Dataset, DatasetDict
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

RANDOM_SEED = 42

# Instruction templates for instruction-tuning format (Polish)
INSTRUCTION_TEMPLATES = [
    "Wyjaśnij poniższy przepis prawny:",
    "Streść następujący fragment aktu prawnego:",
    "Opisz, co reguluje poniższy przepis:",
    "Zinterpretuj poniższy fragment prawa:",
    "Podaj kluczowe informacje z poniższego przepisu:",
    "Wyjaśnij w prostych słowach poniższy artykuł prawny:",
]

# Article/section heading patterns in Polish legal texts
HEADING_PATTERNS = [
    re.compile(r"^(Art(?:ykuł)?\.?\s+\d+[a-z]?(?:\s+\w+)?\.?\s*.{5,80})$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(§\s*\d+[a-z]?\.\s*.{5,80})$", re.MULTILINE),
    re.compile(r"^(Rozdział\s+\w+\.?\s*.{5,80})$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(Dział\s+\w+\.?\s*.{5,80})$", re.MULTILINE | re.IGNORECASE),
]

# Question templates generated from headings
QUESTION_TEMPLATES = [
    "Co stanowi {} w polskim prawie?",
    "Jakie są przepisy dotyczące {}?",
    "Wyjaśnij regulacje prawne dotyczące {}.",
    "Co mówi polskie prawo o {}?",
    "Jakie obowiązki i prawa wynikają z {}?",
]


def load_chunks(path: Path) -> list[dict]:
    """Load all chunk records from a JSONL file."""
    chunks = []
    with path.open(encoding="utf-8") as fh:
        for line in tqdm(fh, desc=f"Loading {path.name}", unit="chunk"):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping bad JSON line")
    return chunks


def make_summary(text: str, max_chars: int = 400) -> str:
    """
    Generate a simple extractive summary of the legal text chunk.
    Takes the first two sentences and the last sentence as a heuristic summary.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return text[:max_chars]

    if len(sentences) <= 3:
        summary = " ".join(sentences)
    else:
        # First two sentences + last sentence
        summary = " ".join(sentences[:2]) + " [...] " + sentences[-1]

    return summary[:max_chars]


def build_instruction_record(chunk: dict, seed: int = 0) -> dict:
    """Create an instruction-tuning record from a chunk."""
    rng = random.Random(seed)
    instruction = rng.choice(INSTRUCTION_TEMPLATES)
    text = chunk["text"]
    output = make_summary(text)

    return {
        "instruction": instruction,
        "input": text,
        "output": output,
        "act_id": chunk.get("act_id", ""),
        "title": chunk.get("title", ""),
        "year": chunk.get("year", ""),
        "chunk_index": chunk.get("chunk_index", 0),
        "source_url": chunk.get("url", ""),
    }


def extract_heading_from_chunk(text: str) -> str | None:
    """Try to find a legal article or section heading in the chunk text."""
    for pattern in HEADING_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            heading = matches[0].strip().rstrip(".")
            # Clean up heading: strip the article number prefix for question generation
            heading = re.sub(r"^(Art(?:ykuł)?\.?\s+\d+[a-z]?\.\s*|§\s*\d+[a-z]?\.\s*)", "", heading).strip()
            if len(heading) > 10:
                return heading
    return None


def build_qa_record(chunk: dict, seed: int = 0) -> dict | None:
    """
    Create a QA pair from a chunk if it contains a heading.
    Returns None if no suitable heading is found.
    """
    rng = random.Random(seed)
    heading = extract_heading_from_chunk(chunk["text"])
    if not heading:
        return None

    question_template = rng.choice(QUESTION_TEMPLATES)
    # Lowercase the heading for embedding in the question
    question = question_template.format(heading.lower())

    return {
        "question": question,
        "context": chunk["text"],
        "answer": make_summary(chunk["text"], max_chars=600),
        "act_id": chunk.get("act_id", ""),
        "title": chunk.get("title", ""),
        "year": chunk.get("year", ""),
        "chunk_index": chunk.get("chunk_index", 0),
        "source_url": chunk.get("url", ""),
    }


def split_records(records: list[dict], train_ratio: float = 0.8, val_ratio: float = 0.1) -> dict[str, list[dict]]:
    """Shuffle and split records into train/val/test."""
    rng = random.Random(RANDOM_SEED)
    shuffled = records.copy()
    rng.shuffle(shuffled)
    n = len(shuffled)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)
    return {
        "train": shuffled[:train_end],
        "validation": shuffled[train_end:val_end],
        "test": shuffled[val_end:],
    }


def records_to_dataset(records: list[dict]) -> Dataset:
    """Convert a list of dicts to a HuggingFace Dataset."""
    if not records:
        return Dataset.from_dict({})
    keys = list(records[0].keys())
    columns = {k: [r.get(k, "") for r in records] for k in keys}
    return Dataset.from_dict(columns)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HuggingFace Dataset from preprocessed legal chunks.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/chunks.jsonl"),
        help="Input chunks JSONL file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/dataset"),
        help="Output directory for HuggingFace datasets",
    )
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Limit number of chunks (useful for testing)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)

    chunks = load_chunks(args.input)
    if args.max_chunks:
        chunks = chunks[: args.max_chunks]
    log.info("Loaded %d chunks", len(chunks))

    # Build instruction-tuning records
    log.info("Building instruction-tuning records …")
    instruct_records = [
        build_instruction_record(chunk, seed=i) for i, chunk in enumerate(tqdm(chunks, unit="chunk"))
    ]
    log.info("  %d instruction records", len(instruct_records))

    # Build QA records (only for chunks with headings)
    log.info("Building QA records …")
    qa_records = []
    for i, chunk in enumerate(tqdm(chunks, unit="chunk")):
        rec = build_qa_record(chunk, seed=i)
        if rec:
            qa_records.append(rec)
    log.info("  %d QA records", len(qa_records))

    # Split and save instruction-tuning dataset
    instruct_splits = split_records(instruct_records, args.train_ratio, args.val_ratio)
    instruct_ds = DatasetDict(
        {split: records_to_dataset(recs) for split, recs in instruct_splits.items()}
    )
    instruct_path = args.output / "instruction"
    instruct_ds.save_to_disk(str(instruct_path))
    log.info("Saved instruction dataset to %s", instruct_path)
    log.info(
        "  train=%d, val=%d, test=%d",
        len(instruct_splits["train"]),
        len(instruct_splits["validation"]),
        len(instruct_splits["test"]),
    )

    # Split and save QA dataset
    if qa_records:
        qa_splits = split_records(qa_records, args.train_ratio, args.val_ratio)
        qa_ds = DatasetDict(
            {split: records_to_dataset(recs) for split, recs in qa_splits.items()}
        )
        qa_path = args.output / "qa"
        qa_ds.save_to_disk(str(qa_path))
        log.info("Saved QA dataset to %s", qa_path)
    else:
        log.warning("No QA records generated (no headings found in chunks)")

    # Also save combined JSONL for easy inspection
    for split_name, records in instruct_splits.items():
        out_file = args.output / f"instruct_{split_name}.jsonl"
        with out_file.open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.info("Also saved JSONL splits to %s", args.output)


if __name__ == "__main__":
    main()
