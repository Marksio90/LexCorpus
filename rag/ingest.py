"""
ingest.py — Embed legal text chunks and store them in Qdrant.

Uses sdadas/mmlw-retrieval-roberta-large (Polish semantic search model)
to generate embeddings, then upserts them into a Qdrant collection
with payloads containing {act_id, title, year, chunk_index, text}.

Usage:
    python rag/ingest.py --input data/processed/chunks.jsonl
    python rag/ingest.py --input data/processed/chunks.jsonl --collection lexcorpus --url http://localhost:6333
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DEFAULT_MODEL = "sdadas/mmlw-retrieval-roberta-large"
DEFAULT_COLLECTION = "lexcorpus"
DEFAULT_QDRANT_URL = "http://localhost:6333"
BATCH_SIZE = 64
VECTOR_DIM = 1024  # mmlw-retrieval-roberta-large output dimension


def get_qdrant_client(url: str, api_key: str | None = None) -> QdrantClient:
    """Create a Qdrant client. Falls back to in-memory client if URL is ':memory:'."""
    if url == ":memory:":
        return QdrantClient(":memory:")
    return QdrantClient(url=url, api_key=api_key, timeout=60)


def ensure_collection(client: QdrantClient, collection_name: str, vector_dim: int) -> None:
    """Create the Qdrant collection if it does not already exist."""
    existing = {c.name for c in client.get_collections().collections}
    if collection_name in existing:
        log.info("Collection '%s' already exists — will upsert into it", collection_name)
        return

    log.info("Creating collection '%s' (dim=%d, cosine distance) …", collection_name, vector_dim)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=qmodels.VectorParams(
            size=vector_dim,
            distance=qmodels.Distance.COSINE,
        ),
    )
    # Create payload indexes for fast filtering
    for field in ("act_id", "year", "title"):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    log.info("Collection created with payload indexes on act_id, year, title")


def load_chunks(path: Path) -> list[dict]:
    """Load chunk records from a JSONL file."""
    chunks = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping invalid JSON line")
    return chunks


def chunk_to_point_id(chunk: dict, index: int) -> str:
    """Generate a stable UUID for a chunk based on its act_id and chunk_index."""
    act_id = str(chunk.get("act_id", ""))
    chunk_index = str(chunk.get("chunk_index", index))
    name = f"{act_id}__chunk{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def build_payload(chunk: dict) -> dict:
    """Build the Qdrant point payload from a chunk record."""
    return {
        "act_id": str(chunk.get("act_id", "")),
        "title": chunk.get("title", ""),
        "year": chunk.get("year", ""),
        "publisher": chunk.get("publisher", "WDU"),
        "pos": str(chunk.get("pos", "")),
        "url": chunk.get("url", ""),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "total_chunks": int(chunk.get("total_chunks", 1)),
        "text": chunk.get("text", ""),
        "approx_tokens": int(chunk.get("approx_tokens", 0)),
    }


def ingest_chunks(
    chunks: list[dict],
    model: SentenceTransformer,
    client: QdrantClient,
    collection_name: str,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Embed chunks in batches and upsert into Qdrant. Returns number of points upserted."""
    total_upserted = 0
    texts = [c.get("text", "") for c in chunks]

    log.info("Embedding %d chunks (batch_size=%d) …", len(chunks), batch_size)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # cosine similarity via dot product
        convert_to_numpy=True,
    )

    log.info("Upserting into Qdrant collection '%s' …", collection_name)
    for batch_start in tqdm(range(0, len(chunks), batch_size), desc="Upserting", unit="batch"):
        batch_chunks = chunks[batch_start : batch_start + batch_size]
        batch_embeddings = embeddings[batch_start : batch_start + batch_size]

        points = [
            qmodels.PointStruct(
                id=chunk_to_point_id(chunk, batch_start + i),
                vector=embedding.tolist(),
                payload=build_payload(chunk),
            )
            for i, (chunk, embedding) in enumerate(zip(batch_chunks, batch_embeddings))
        ]

        client.upsert(collection_name=collection_name, points=points, wait=True)
        total_upserted += len(points)

    return total_upserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed legal chunks and ingest into Qdrant.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/chunks.jsonl"),
        help="Input JSONL file with chunked legal texts",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_QDRANT_URL,
        help="Qdrant server URL (use ':memory:' for in-memory mode)",
    )
    parser.add_argument("--api-key", default=None, help="Qdrant API key (for cloud)")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="SentenceTransformer model for embeddings",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Limit number of chunks (for testing)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        sys.exit(1)

    log.info("Loading chunks from %s …", args.input)
    chunks = load_chunks(args.input)
    log.info("Loaded %d chunks", len(chunks))

    if args.max_chunks:
        chunks = chunks[: args.max_chunks]
        log.info("Limiting to %d chunks", len(chunks))

    if not chunks:
        log.error("No chunks to ingest")
        sys.exit(1)

    log.info("Loading embedding model '%s' …", args.model)
    model = SentenceTransformer(args.model)
    vector_dim = model.get_sentence_embedding_dimension()
    log.info("Model loaded. Embedding dimension: %d", vector_dim)

    log.info("Connecting to Qdrant at %s …", args.url)
    client = get_qdrant_client(args.url, args.api_key)

    ensure_collection(client, args.collection, vector_dim)

    n = ingest_chunks(chunks, model, client, args.collection, args.batch_size)
    log.info("Done. Upserted %d points into collection '%s'", n, args.collection)

    # Print collection info
    info = client.get_collection(args.collection)
    log.info(
        "Collection stats: %d vectors, status=%s",
        info.vectors_count,
        info.status,
    )


if __name__ == "__main__":
    main()
