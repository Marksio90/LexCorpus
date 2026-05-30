"""
enrich_ner.py — Apply Polish Legal NER to chunks.jsonl and update Qdrant payloads.

Two operations:
1. Offline: reads chunks.jsonl, runs NER, writes chunks_ner.jsonl (adds 'entities' field)
2. Online:  pushes enriched payloads to Qdrant (set_payload) — no re-embedding needed

The 'entities' field added to each chunk:
    [{"text": "art. 15", "label": "ARTICLE", "score": 1.0}, ...]

This enables structured Qdrant filtering:
    filter = {"must": [{"key": "entities[].label", "match": {"value": "LAW"}}]}

Usage:
    # Step 1 — enrich JSONL (no Qdrant required)
    python scripts/enrich_ner.py \\
        --input data/processed/chunks.jsonl \\
        --output data/processed/chunks_ner.jsonl

    # Step 2 — push to Qdrant
    python scripts/enrich_ner.py \\
        --input data/processed/chunks_ner.jsonl \\
        --push-to-qdrant \\
        --collection legal_docs

Requirements:
    pip install qdrant-client  (for --push-to-qdrant)
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

BATCH_SIZE = 200


def _load_chunks(path: Path) -> list[dict]:
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return chunks


def enrich_chunks(chunks: list[dict], ner, skip_existing: bool) -> list[dict]:
    enriched = []
    for chunk in chunks:
        if skip_existing and chunk.get("entities"):
            enriched.append(chunk)
            continue
        result = ner.extract(chunk.get("text", ""))
        enriched.append({
            **chunk,
            "entities": [
                {"text": e.text, "label": e.label, "score": round(e.score, 4)}
                for e in result.entities
            ],
        })
    return enriched


def push_to_qdrant(
    chunks_ner: list[dict],
    collection: str,
    qdrant_url: str,
    qdrant_api_key: str | None,
) -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointIdsList, SetPayload
    except ImportError:
        log.error("qdrant-client required: pip install qdrant-client")
        sys.exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

    # Check collection exists
    collections = [c.name for c in client.get_collections().collections]
    if collection not in collections:
        log.error("Collection '%s' not found in Qdrant. Run ingest.py first.", collection)
        sys.exit(1)

    # Build act_id+chunk_index → entities map from enriched chunks
    updated = 0
    errors = 0

    for i in range(0, len(chunks_ner), BATCH_SIZE):
        batch = chunks_ner[i: i + BATCH_SIZE]

        # Scroll to find matching point IDs by act_id+chunk_index
        for chunk in batch:
            act_id = chunk.get("act_id", "")
            chunk_index = chunk.get("chunk_index", 0)
            entities = chunk.get("entities", [])

            if not entities:
                continue

            # Search for the point by payload filter
            results, _ = client.scroll(
                collection_name=collection,
                scroll_filter={
                    "must": [
                        {"key": "act_id", "match": {"value": act_id}},
                        {"key": "chunk_index", "match": {"value": chunk_index}},
                    ]
                },
                limit=1,
                with_payload=False,
                with_vectors=False,
            )

            if not results:
                continue

            point_id = results[0].id
            try:
                client.set_payload(
                    collection_name=collection,
                    payload={"entities": entities},
                    points=[point_id],
                )
                updated += 1
            except Exception as exc:
                log.warning("Failed to update point %s: %s", point_id, exc)
                errors += 1

        done = min(i + BATCH_SIZE, len(chunks_ner))
        log.info("[%d/%d] updated=%d errors=%d", done, len(chunks_ner), updated, errors)

    log.info("Done. Updated %d points in Qdrant collection '%s'", updated, collection)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich chunks with Polish Legal NER entities")
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunks_ner.jsonl"))
    parser.add_argument("--model-path", default=os.getenv("NER_MODEL_PATH", "output/herbert-legal-ner"),
                        help="Path to fine-tuned HerBERT NER model (or empty for regex fallback)")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip chunks that already have 'entities' field")
    parser.add_argument("--push-to-qdrant", action="store_true",
                        help="Also push enriched payloads to Qdrant (requires qdrant-client)")
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "legal_docs"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY"))
    parser.add_argument("--dry-run", action="store_true", help="Show stats without writing output")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rag.ner import PolishLegalNER

    if not args.input.exists():
        log.error("Input not found: %s", args.input)
        sys.exit(1)

    log.info("Loading chunks from %s …", args.input)
    chunks = _load_chunks(args.input)
    log.info("Loaded %d chunks", len(chunks))

    if args.max_chunks:
        chunks = chunks[: args.max_chunks]

    log.info("Initialising NER (model_path=%s) …", args.model_path)
    ner = PolishLegalNER(model_path=args.model_path, device=args.device)

    if args.dry_run:
        sample = chunks[:5]
        for chunk in sample:
            result = ner.extract(chunk.get("text", ""))
            print(f"\nChunk: {chunk.get('act_id')}[{chunk.get('chunk_index')}]")
            for e in result.entities[:5]:
                print(f"  [{e.label}] {e.text!r}")
        return

    log.info("Enriching %d chunks with NER …", len(chunks))
    start = time.time()
    chunks_ner = enrich_chunks(chunks, ner, args.skip_existing)

    entity_count = sum(len(c.get("entities", [])) for c in chunks_ner)
    elapsed = time.time() - start
    log.info(
        "Enriched in %.1fs. Total entities: %d (avg %.1f per chunk)",
        elapsed, entity_count, entity_count / max(1, len(chunks_ner))
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for chunk in chunks_ner:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    log.info("Written %d chunks to %s", len(chunks_ner), args.output)

    # Label distribution
    by_label: dict[str, int] = {}
    for chunk in chunks_ner:
        for ent in chunk.get("entities", []):
            by_label[ent["label"]] = by_label.get(ent["label"], 0) + 1
    log.info("Entity distribution: %s", by_label)

    if args.push_to_qdrant:
        log.info("Pushing NER payloads to Qdrant collection '%s' …", args.collection)
        push_to_qdrant(chunks_ner, args.collection, args.qdrant_url, args.qdrant_api_key)


if __name__ == "__main__":
    main()
