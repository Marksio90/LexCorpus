"""
ingest.py — Embed legal text chunks and store them in Qdrant with hybrid vectors.

Stores both dense (sentence-transformers) and sparse (BM25 via fastembed) vectors
in a single Qdrant collection, enabling hybrid search with RRF fusion at query time.

Usage:
    python rag/ingest.py --input data/processed/chunks.jsonl
    python rag/ingest.py --input data/processed/chunks.jsonl --qdrant http://localhost:6333
    python rag/ingest.py --input data/processed/chunks.jsonl --recreate
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from fastembed.sparse.bm25 import Bm25
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
DEFAULT_QDRANT_PATH = "data/qdrant"
BATCH_SIZE = 64
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_qdrant_client(path_or_url: str, api_key: str | None = None) -> QdrantClient:
    if path_or_url == ":memory:":
        return QdrantClient(":memory:")
    if path_or_url.startswith("http"):
        return QdrantClient(url=path_or_url, api_key=api_key, timeout=60)
    Path(path_or_url).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=path_or_url)


def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_dim: int,
    recreate: bool = False,
) -> None:
    existing = {c.name for c in client.get_collections().collections}

    if collection_name in existing:
        if recreate:
            log.info("Deleting existing collection '%s' (--recreate)", collection_name)
            client.delete_collection(collection_name)
        else:
            log.info("Collection '%s' already exists — will upsert into it", collection_name)
            return

    log.info("Creating collection '%s' (dense_dim=%d, + BM25 sparse) …", collection_name, vector_dim)
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: qmodels.VectorParams(
                size=vector_dim,
                distance=qmodels.Distance.COSINE,
            )
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(
                index=qmodels.SparseIndexParams(on_disk=False)
            )
        },
    )
    for field in ("act_id", "year", "title"):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    for field in ("publisher", "source_type", "chunk_index"):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    log.info("Collection created with dense + sparse vectors and payload indexes")


def load_chunks(path: Path) -> list[dict]:
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
    act_id = str(chunk.get("act_id", ""))
    chunk_index = str(chunk.get("chunk_index", index))
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{act_id}__chunk{chunk_index}"))


PUBLISHER_TO_SOURCE = {
    "WDU": "legislation", "WMP": "legislation",
    "ADMINISTRATIVE": "judgment_nsa", "SUPREME": "judgment_sn",
    "CONSTITUTIONAL_TRIBUNAL": "judgment_tk", "COMMON": "judgment_common",
    "NATIONAL_APPEAL_CHAMBER": "judgment_kio",
}


def build_payload(chunk: dict) -> dict:
    publisher = chunk.get("publisher", "WDU")
    return {
        "act_id": str(chunk.get("act_id", "")),
        "title": chunk.get("title", ""),
        "year": chunk.get("year", ""),
        "publisher": publisher,
        "source_type": PUBLISHER_TO_SOURCE.get(publisher, "legislation"),
        "pos": str(chunk.get("pos", "")),
        "url": chunk.get("url", ""),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "total_chunks": int(chunk.get("total_chunks", 1)),
        "text": chunk.get("text", ""),
        "approx_tokens": int(chunk.get("approx_tokens", 0)),
    }


def ingest_chunks(
    chunks: list[dict],
    dense_model: SentenceTransformer,
    sparse_model: Bm25,
    client: QdrantClient,
    collection_name: str,
    batch_size: int = BATCH_SIZE,
) -> int:
    texts = [c.get("text", "") for c in chunks]

    log.info("Computing dense embeddings for %d chunks …", len(chunks))
    dense_embeddings = dense_model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    log.info("Computing sparse BM25 embeddings …")
    sparse_embeddings = list(tqdm(sparse_model.embed(texts), total=len(texts), desc="BM25", unit="chunk"))

    log.info("Upserting into Qdrant collection '%s' …", collection_name)
    total_upserted = 0
    for batch_start in tqdm(range(0, len(chunks), batch_size), desc="Upserting", unit="batch"):
        batch_chunks = chunks[batch_start : batch_start + batch_size]
        batch_dense = dense_embeddings[batch_start : batch_start + batch_size]
        batch_sparse = sparse_embeddings[batch_start : batch_start + batch_size]

        points = [
            qmodels.PointStruct(
                id=chunk_to_point_id(chunk, batch_start + i),
                vector={
                    DENSE_VECTOR_NAME: dense_vec.tolist(),
                    SPARSE_VECTOR_NAME: qmodels.SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
                payload=build_payload(chunk),
            )
            for i, (chunk, dense_vec, sparse_vec) in enumerate(zip(batch_chunks, batch_dense, batch_sparse))
        ]

        client.upsert(collection_name=collection_name, points=points, wait=True)
        total_upserted += len(points)

    return total_upserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed legal chunks and ingest into Qdrant (hybrid: dense + BM25).")
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant", default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="SentenceTransformer model for dense embeddings")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--max-chunks", type=int, default=None, help="Limit chunks (for testing)")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate collection if it exists")
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

    log.info("Loading dense model '%s' …", args.model)
    dense_model = SentenceTransformer(args.model)
    vector_dim = dense_model.get_sentence_embedding_dimension()
    log.info("Dense model loaded. dim=%d", vector_dim)

    log.info("Loading BM25 sparse model …")
    sparse_model = Bm25("Qdrant/bm25")
    log.info("BM25 model loaded.")

    client = get_qdrant_client(args.qdrant, args.api_key)
    ensure_collection(client, args.collection, vector_dim, recreate=args.recreate)

    n = ingest_chunks(chunks, dense_model, sparse_model, client, args.collection, args.batch_size)
    log.info("Done. Upserted %d points into '%s'", n, args.collection)

    info = client.get_collection(args.collection)
    points_count = getattr(info, "points_count", None) or getattr(info, "vectors_count", "?")
    log.info("Collection stats: %s points, status=%s", points_count, info.status)


if __name__ == "__main__":
    main()
