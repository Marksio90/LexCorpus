"""
generate_contextual_chunks.py — Contextual Retrieval enrichment (Anthropic, 2024).

For each chunk in chunks.jsonl, calls an LLM to generate a short context prefix
describing which act/judgment the chunk comes from and what it covers. This prefix
is stored in the 'ctx_prefix' field and prepended to the chunk text at embed time,
dramatically improving retrieval accuracy (Anthropic reports 67% fewer failures).

The enriched JSONL is written to data/processed/chunks_contextual.jsonl and can be
used as a drop-in replacement for chunks.jsonl before re-ingesting.

Run once before re-ingesting:
    python scripts/generate_contextual_chunks.py \\
        --input data/processed/chunks.jsonl \\
        --output data/processed/chunks_contextual.jsonl \\
        --max-chunks 50000

Cost estimate: ~$1.50 per 100k chunks with gpt-4o-mini (3 tokens/request avg).

Then re-ingest:
    rm data/qdrant/.ingested
    docker compose up ingest
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ISAP_SYSTEM = (
    "Jesteś asystentem do indeksowania polskich aktów prawnych. "
    "Napisz krótki kontekst (1-2 zdania) opisujący skąd pochodzi poniższy fragment aktu prawnego. "
    "Podaj: nazwę ustawy/rozporządzenia, rok, rozdział (jeśli widoczny), i o czym ogólnie mówi ten fragment. "
    "Odpowiedz TYLKO tym krótkim opisem — bez żadnego wstępu ani wyjaśnień."
)

SAOS_SYSTEM = (
    "Jesteś asystentem do indeksowania polskich wyroków sądowych. "
    "Napisz krótki kontekst (1-2 zdania) opisujący skąd pochodzi poniższy fragment orzeczenia. "
    "Podaj: sąd, numer sprawy (jeśli widoczny w tytule), rok i czego dotyczy ten fragment. "
    "Odpowiedz TYLKO tym krótkim opisem — bez żadnego wstępu ani wyjaśnień."
)

BATCH_SIZE = 20         # concurrent requests per batch (stay within rate limits)
REQUEST_DELAY = 0.05    # seconds between batches


def _is_saos(chunk: dict) -> bool:
    pub = chunk.get("publisher", "WDU")
    return pub in ("ADMINISTRATIVE", "SUPREME", "CONSTITUTIONAL_TRIBUNAL", "COMMON", "NATIONAL_APPEAL_CHAMBER")


def _build_user_message(chunk: dict) -> str:
    title = chunk.get("title", "")
    text = chunk.get("text", "")[:800]  # limit to 800 chars to keep token count low
    if title:
        return f"Tytuł dokumentu: {title}\n\nFragment tekstu:\n{text}"
    return f"Fragment tekstu:\n{text}"


def generate_ctx_prefix(chunk: dict, client, model: str) -> str:
    """Call LLM to generate a 1-2 sentence context prefix for a single chunk."""
    system = SAOS_SYSTEM if _is_saos(chunk) else ISAP_SYSTEM
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _build_user_message(chunk)},
            ],
            temperature=0.0,
            max_tokens=120,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log.warning("LLM failed for chunk %s[%s]: %s", chunk.get("act_id"), chunk.get("chunk_index"), exc)
        return ""


def process_batch(
    batch: list[dict],
    client,
    model: str,
    skip_existing: bool,
) -> list[dict]:
    """Enrich a batch of chunks with ctx_prefix."""
    results = []
    for chunk in batch:
        if skip_existing and chunk.get("ctx_prefix"):
            results.append(chunk)
            continue
        prefix = generate_ctx_prefix(chunk, client, model)
        if prefix:
            chunk = {**chunk, "ctx_prefix": prefix}
        results.append(chunk)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich chunks.jsonl with LLM-generated context prefixes for Contextual Retrieval."
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunks_contextual.jsonl"))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-chunks", type=int, default=None, help="Limit chunks (for testing)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip chunks that already have ctx_prefix (for resuming)")
    parser.add_argument("--saos-only", action="store_true", help="Enrich only SAOS court judgment chunks")
    parser.add_argument("--isap-only", action="store_true", help="Enrich only ISAP legislation chunks")
    parser.add_argument("--dry-run", action="store_true", help="Print first 3 prefixes without writing output")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY not set")
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        log.error("openai package required: pip install openai")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        sys.exit(1)

    log.info("Loading chunks from %s …", args.input)
    chunks: list[dict] = []
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Apply source filter if requested
            if args.saos_only and not _is_saos(chunk):
                continue
            if args.isap_only and _is_saos(chunk):
                continue
            chunks.append(chunk)

    log.info("Loaded %d chunks", len(chunks))

    if args.max_chunks:
        chunks = chunks[: args.max_chunks]
        log.info("Limited to %d chunks", len(chunks))

    if args.dry_run:
        log.info("DRY RUN — generating prefixes for first 3 chunks:")
        for chunk in chunks[:3]:
            prefix = generate_ctx_prefix(chunk, client, args.model)
            print(f"\nChunk: {chunk.get('act_id')}[{chunk.get('chunk_index')}]")
            print(f"Title: {chunk.get('title', '')[:80]}")
            print(f"Generated prefix: {prefix}")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)

    enriched = 0
    skipped = 0
    total = len(chunks)
    start = time.time()

    with args.output.open("w", encoding="utf-8") as fout:
        for batch_start in range(0, total, args.batch_size):
            batch = chunks[batch_start: batch_start + args.batch_size]
            enriched_batch = process_batch(batch, client, args.model, args.skip_existing)

            for chunk in enriched_batch:
                fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                if chunk.get("ctx_prefix"):
                    enriched += 1
                else:
                    skipped += 1

            done = min(batch_start + args.batch_size, total)
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            log.info(
                "[%d/%d] enriched=%d  skipped=%d  %.1f chunks/s  ETA: %.0fs",
                done, total, enriched, skipped, rate, eta,
            )
            time.sleep(REQUEST_DELAY)

    elapsed = time.time() - start
    log.info(
        "Done in %.1fs. Enriched: %d/%d chunks with ctx_prefix. Output: %s",
        elapsed, enriched, total, args.output,
    )
    log.info(
        "Estimated cost: ~$%.2f (gpt-4o-mini @ $0.15/1M input tokens, ~80 tokens/chunk avg)",
        enriched * 80 * 0.15 / 1_000_000,
    )
    log.info(
        "Next step: rm data/qdrant/.ingested && "
        "python rag/ingest.py --input %s --recreate",
        args.output,
    )


if __name__ == "__main__":
    main()
