"""
generate_training_data.py — Synthetic Q&A generation using GPT-4o.

For each legal chunk, calls GPT-4o to generate realistic question-answer pairs
in the format the model will see during RAG inference (with [N] citations).

This is the "teacher distillation" approach: GPT-4o reads Polish legal texts
and generates high-quality training examples we couldn't get otherwise.

Output format (JSONL):
  {
    "messages": [
      {"role": "system",  "content": "..."},
      {"role": "user",    "content": "PRZEPISY:\\n[1] ...\\n\\nPYTANIE: ..."},
      {"role": "assistant","content": "answer with [1] citations"}
    ],
    "act_id": "...",
    "source_type": "legislation|judgment_nsa|...",
    "year": "2024"
  }

Usage:
    python scripts/generate_training_data.py \\
        --input data/processed/chunks.jsonl \\
        --output data/dataset/synthetic \\
        --max-chunks 5000 \\
        --questions-per-chunk 2

    # Resume interrupted run (skips already cached chunks):
    python scripts/generate_training_data.py --resume

    # Dry run (no API calls):
    python scripts/generate_training_data.py --dry-run --max-chunks 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Jesteś ekspertem ds. polskiego prawa. Odpowiadasz na pytania prawne "
    "na podstawie podanych przepisów prawa polskiego. "
    "Udzielasz dokładnych, zwięzłych odpowiedzi w języku polskim. "
    "Zawsze powołujesz się na konkretne artykuły i akty prawne używając znaczników [1], [2] itd. "
    "odpowiadających numeracji podanych przepisów."
)

GENERATOR_SYSTEM = (
    "Jesteś generatorem danych treningowych dla polskiego asystenta prawnego. "
    "Na podstawie podanego fragmentu aktu prawnego lub orzeczenia, wygenerujesz "
    "realistyczne pytania prawne i wzorcowe odpowiedzi. "
    "Pytania muszą być konkretne i praktyczne — takie, jakie zadałby prawnik lub obywatel. "
    "Odpowiedzi muszą być precyzyjne, oparte wyłącznie na podanym tekście, "
    "i zawierać cytowanie [1] przy każdym twierdzeniu."
)

GENERATOR_PROMPT = """\
Na podstawie poniższego fragmentu aktu prawnego/orzeczenia wygeneruj {n} par pytanie-odpowiedź.

FRAGMENT:
Tytuł: {title}
Rok: {year}
Treść:
{text}

Zwróć odpowiedź jako tablicę JSON (i TYLKO tablicę JSON, bez żadnego dodatkowego tekstu):
[
  {{
    "question": "...",
    "answer": "... [1] ..."
  }},
  ...
]

Wymagania:
- Pytania: praktyczne, po polsku, różne typy (co?, kiedy?, ile?, jak?, czy?)
- Odpowiedzi: na podstawie WYŁĄCZNIE podanego tekstu, z cytowaniem [1]
- Nie wymyślaj faktów spoza podanego tekstu
- Każda odpowiedź: 2-5 zdań
"""

PUBLISHER_TO_SOURCE_TYPE = {
    "WDU": "legislation",
    "WMP": "legislation",
    "ADMINISTRATIVE": "judgment_nsa",
    "SUPREME": "judgment_sn",
    "CONSTITUTIONAL_TRIBUNAL": "judgment_tk",
    "COMMON": "judgment_common",
    "NATIONAL_APPEAL_CHAMBER": "judgment_kio",
}


def load_chunks(path: Path, max_chunks: int | None, source_filter: str | None) -> list[dict]:
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Skip very short chunks
            if len(c.get("text", "")) < 100:
                continue
            # Apply source filter
            if source_filter:
                if c.get("publisher", "") not in source_filter.split(","):
                    continue
            chunks.append(c)
            if max_chunks and len(chunks) >= max_chunks:
                break
    return chunks


def load_cache(cache_file: Path) -> set[str]:
    """Return set of already-processed chunk keys."""
    if not cache_file.exists():
        return set()
    seen = set()
    with cache_file.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                seen.add(rec.get("_chunk_key", ""))
            except Exception:
                pass
    return seen


def chunk_key(chunk: dict) -> str:
    return f"{chunk['act_id']}___{chunk.get('chunk_index', 0)}"


def call_gpt4o(client, chunk: dict, n_questions: int, dry_run: bool) -> list[dict]:
    """Call GPT-4o to generate n_questions Q&A pairs for this chunk. Returns list of {question, answer}."""
    if dry_run:
        return [
            {
                "question": f"[DRY RUN] Pytanie dotyczące: {chunk['title'][:50]}?",
                "answer": f"[DRY RUN] Odpowiedź na podstawie fragmentu [1]. {chunk['text'][:100]}",
            }
        ]

    prompt = GENERATOR_PROMPT.format(
        n=n_questions,
        title=chunk.get("title", "Nieznany akt"),
        year=chunk.get("year", ""),
        text=chunk["text"][:2000],  # cap to avoid token overflow
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # cheaper; use gpt-4o for higher quality
            messages=[
                {"role": "system", "content": GENERATOR_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            max_tokens=800,
            response_format={"type": "json_object"} if False else None,  # json_object doesn't support arrays
        )
        raw = response.choices[0].message.content.strip()
        # The response should be a JSON array
        if raw.startswith("["):
            pairs = json.loads(raw)
        else:
            # Try extracting array from somewhere in the response
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                pairs = json.loads(raw[start:end])
            else:
                log.warning("Could not parse JSON array from response: %s", raw[:200])
                return []
        return [p for p in pairs if isinstance(p, dict) and "question" in p and "answer" in p]
    except Exception as exc:
        log.warning("GPT-4o call failed: %s", exc)
        return []


def build_training_record(chunk: dict, question: str, answer: str) -> dict:
    """Build a chat-format training record matching the RAG inference format."""
    source_type = PUBLISHER_TO_SOURCE_TYPE.get(chunk.get("publisher", ""), "unknown")
    citation_header = f"[1] {chunk.get('title', chunk['act_id'])} ({chunk.get('year', '')})"
    if chunk.get("pos"):
        citation_header += f" poz. {chunk['pos']}"

    user_content = (
        f"Na podstawie poniższych przepisów prawnych odpowiedz na pytanie. "
        f"Cytuj źródła używając numerów w nawiasach kwadratowych.\n\n"
        f"PRZEPISY:\n{citation_header}\n{chunk['text']}\n\n"
        f"PYTANIE: {question}\n\n"
        f"ODPOWIEDŹ (powołuj się na [1] przy każdym twierdzeniu):"
    )

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_content},
            {"role": "assistant", "content": answer},
        ],
        "act_id":      chunk.get("act_id", ""),
        "source_type": source_type,
        "year":        str(chunk.get("year", "")),
        "chunk_index": chunk.get("chunk_index", 0),
        "_chunk_key":  chunk_key(chunk),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic legal Q&A training data using GPT-4o.")
    parser.add_argument("--input",   type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--output",  type=Path, default=Path("data/dataset/synthetic"))
    parser.add_argument("--max-chunks",  type=int, default=5000, help="Max chunks to process (0=all)")
    parser.add_argument("--questions-per-chunk", type=int, default=2)
    parser.add_argument("--model",   default="gpt-4o-mini", help="gpt-4o-mini (cheap) or gpt-4o (quality)")
    parser.add_argument("--source-filter", default=None, help="Comma-separated publishers to include, e.g. WDU,ADMINISTRATIVE")
    parser.add_argument("--resume",  action="store_true", help="Skip already-generated chunks (reads output file)")
    parser.add_argument("--dry-run", action="store_true", help="No API calls — generate dummy data")
    parser.add_argument("--seed",    type=int, default=42)
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input not found: %s", args.input)
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        log.error("OPENAI_API_KEY not set. Use --dry-run to test without API.")
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)
    out_file = args.output / "training_data.jsonl"
    cache_file = out_file  # same file used as cache

    random.seed(args.seed)

    max_chunks = args.max_chunks if args.max_chunks > 0 else None
    chunks = load_chunks(args.input, max_chunks, args.source_filter)
    log.info("Loaded %d chunks", len(chunks))

    # Shuffle for variety across source types
    random.shuffle(chunks)

    # Resume: skip already processed
    already_done = load_cache(cache_file) if args.resume else set()
    if already_done:
        log.info("Resuming — skipping %d already processed chunks", len(already_done))
        chunks = [c for c in chunks if chunk_key(c) not in already_done]

    client = None
    if not args.dry_run:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # Override model in client calls
        global _model
        _model = args.model

    total_records = 0
    errors = 0
    start_time = time.time()

    with out_file.open("a", encoding="utf-8") as fout:
        for i, chunk in enumerate(chunks):
            if i % 100 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(chunks) - i) / rate if rate > 0 else 0
                log.info(
                    "[%d/%d] generated=%d errors=%d rate=%.1f/s ETA=%.0fs",
                    i, len(chunks), total_records, errors, rate, eta,
                )

            pairs = call_gpt4o(client, chunk, args.questions_per_chunk, args.dry_run)
            if not pairs:
                errors += 1
                # Rate limit backoff
                if not args.dry_run:
                    time.sleep(1)
                continue

            for pair in pairs:
                record = build_training_record(chunk, pair["question"], pair["answer"])
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_records += 1

            # Rate limiting — gpt-4o-mini allows ~500 RPM
            if not args.dry_run:
                time.sleep(0.15)

    elapsed = time.time() - start_time
    log.info(
        "Done. %d training records from %d chunks in %.0fs (%.1f records/chunk, %d errors)",
        total_records, len(chunks), elapsed,
        total_records / max(len(chunks), 1), errors,
    )
    log.info("Output: %s", out_file)

    # Split into train/val/test
    _split_output(out_file, args.output)


def _split_output(jsonl_file: Path, output_dir: Path, train_ratio: float = 0.85, val_ratio: float = 0.1) -> None:
    """Split generated JSONL into train/val/test files."""
    records = []
    with jsonl_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    random.shuffle(records)
    n = len(records)
    train_end = int(n * train_ratio)
    val_end = train_end + int(n * val_ratio)

    splits = {
        "train": records[:train_end],
        "val": records[train_end:val_end],
        "test": records[val_end:],
    }

    for split_name, split_records in splits.items():
        out = output_dir / f"{split_name}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for r in split_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        log.info("  %s: %d records → %s", split_name, len(split_records), out)


if __name__ == "__main__":
    main()
